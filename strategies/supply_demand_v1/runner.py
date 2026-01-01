"""Supply & Demand V1 Experiment Runner

This module provides infrastructure to run repeatable backtests across multiple symbols
and time ranges, outputting machine-readable artifacts for comparison between PRs.

Key Functions:
    - run_backtest_experiment: Main entry point for running experiments
    - generate_synthetic_candles: Create synthetic OHLC data for testing
    - execute_backtest_for_symbol: Run strategy on a single symbol
    - collect_artifacts: Aggregate results into standardized format

Artifacts Generated:
    - summary.json: Aggregate metrics + per-symbol breakdown
    - trades.csv: All trades with full details
    - zones.csv: All zones detected with scoring info
    - run_manifest.json: Metadata about the run (git commit, config, etc.)
    - violations.json: Integrity check results
"""

import os
import sys
import json
import csv
import hashlib
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import random

import yaml

# Add repo root to path for imports
repo_root = Path(__file__).parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    TradePlan,
    OrderState,
    CurveLocation,
    TrendDirection,
    EntryMode,
    detect_zones_dbr_rbd,
    is_zone_fresh,
    find_nearest_fresh_zones_htf,
    curve_location,
    trend_direction_itf,
    odds_enhancer_score,
    build_trade_plan,
    should_allow_trade,
    check_limit_order_fill,
    check_intrabar_exit,
    manage_trade_plan,
    calculate_pnl_with_costs,
)

from strategies.supply_demand_v1.integrity import (
    validate_no_lookahead,
    validate_entry_after_zone_creation,
    validate_planned_r_calculation,
    validate_minimum_r,
    IntegrityReport,
    ViolationType,
)


@dataclass
class SymbolResult:
    """Results for a single symbol backtest"""
    symbol: str
    total_zones: int
    fresh_zones: int
    trades_placed: int
    trades_filled: int
    trades_won: int
    trades_lost: int
    total_pnl: float
    win_rate: float
    avg_r_realized: float
    max_drawdown: float
    final_capital: float


@dataclass
class ExperimentResult:
    """Complete experiment result with all artifacts"""
    config: Dict[str, Any]
    symbol_results: List[SymbolResult]
    all_trades: List[Dict[str, Any]]
    all_zones: List[Dict[str, Any]]
    aggregate_metrics: Dict[str, Any]
    integrity_report: IntegrityReport
    run_manifest: Dict[str, Any]


def generate_synthetic_candles(
    symbol: str,
    num_candles: int,
    base_price: float = 100.0,
    volatility: float = 0.02,
    seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generate synthetic OHLC candle data for testing
    
    Creates realistic price action with trends, consolidations, and volatility.
    
    Args:
        symbol: Trading pair symbol
        num_candles: Number of candles to generate
        base_price: Starting price
        volatility: Price movement volatility (0.02 = 2%)
        seed: Random seed for reproducibility
    
    Returns:
        List of candle dicts with keys: open, high, low, close, volume, timestamp
    """
    if seed is not None:
        random.seed(seed)
    
    candles = []
    current_price = base_price
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    for i in range(num_candles):
        # Random walk with trend bias
        trend_bias = random.choice([-1, 0, 1]) * volatility * 0.5
        price_change = random.gauss(trend_bias, volatility)
        
        # Open price
        open_price = current_price
        
        # Close price
        close_price = open_price * (1 + price_change)
        
        # High and low with realistic wicks
        wick_size = abs(price_change) * random.uniform(0.3, 0.7)
        if close_price > open_price:  # Bullish candle
            high = close_price * (1 + wick_size)
            low = open_price * (1 - wick_size)
        else:  # Bearish candle
            high = open_price * (1 + wick_size)
            low = close_price * (1 - wick_size)
        
        # Volume (random but realistic)
        volume = random.uniform(100000, 1000000)
        
        candle = {
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price,
            'volume': volume,
            'timestamp': timestamp,
            'symbol': symbol,
        }
        candles.append(candle)
        
        current_price = close_price
        timestamp = timestamp + timedelta(minutes=15)  # 15m candles
    
    return candles


def execute_backtest_for_symbol(
    symbol: str,
    candles: List[Dict[str, Any]],
    params: SupplyDemandParameters,
    initial_capital: float
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """Execute backtest for a single symbol
    
    Args:
        symbol: Trading pair symbol
        candles: OHLC candle data
        params: Strategy parameters
        initial_capital: Starting capital
    
    Returns:
        Tuple of (trades, zones, final_capital)
    """
    # Detect all zones
    zones = detect_zones_dbr_rbd(candles, params)
    
    # Track capital and positions
    capital = initial_capital
    trades = []
    pending_plans = []  # Plans with pending orders
    open_positions = []  # Plans with filled orders (active positions)
    
    # Simulate backtest bar by bar
    for idx in range(len(candles)):
        candle = candles[idx]
        
        # Update zone freshness
        for zone in zones:
            if zone.created_at < idx:
                is_zone_fresh(zone, candles, idx)
        
        # Check for fills on pending orders
        for plan in list(pending_plans):
            if plan.order_state == OrderState.PENDING:
                # Check TTL expiration first
                if params.ttl_bars and (idx - plan.placed_at_idx) >= params.ttl_bars:
                    plan.order_state = OrderState.CANCELLED
                    pending_plans.remove(plan)
                    # Note: TTL cancellation doesn't create a trade record (never filled)
                    continue
                
                # Check for fill
                filled = check_limit_order_fill(
                    plan,
                    candles,
                    idx,
                    params
                )
                if filled:
                    plan.order_state = OrderState.FILLED
                    plan.filled_at_idx = idx
                    
                    # Move from pending to open positions
                    pending_plans.remove(plan)
                    open_positions.append(plan)
                    
                    # Create trade record (entry)
                    trades.append({
                        'symbol': symbol,
                        'side': 'LONG' if plan.zone.zone_type == ZoneType.DEMAND else 'SHORT',
                        'entry': plan.actual_entry_price or plan.entry_price,
                        'stop': plan.stop_loss,
                        'target': plan.take_profit,
                        'planned_R': plan.r_multiple,
                        'planned_r': plan.r_multiple,  # Add lowercase for integrity validation
                        'realized_R': None,  # Will be filled on exit
                        'entry_time': candle.get('timestamp'),
                        'entry_idx': idx,
                        'exit_time': None,
                        'exit_idx': None,
                        'exit_reason': None,
                        'score': plan.score,
                        # curve_state and trend_state removed until properly implemented
                        'zone_created_at': plan.zone.created_at,
                        'pnl': 0.0,
                        'position_size': plan.position_size,
                    })
        
        # Check for exits on open positions
        for plan in list(open_positions):
            is_long = plan.zone.zone_type == ZoneType.DEMAND
            
            # Check for intrabar stop or target hit
            exit_reason = check_intrabar_exit(
                plan,
                candle,
                params,
                stop_wins_on_same_bar=True  # Conservative: stop wins if both hit
            )
            
            if exit_reason:
                # Determine exit price based on reason
                if exit_reason == "STOP":
                    exit_price = plan.stop_loss
                elif exit_reason == "TARGET":
                    exit_price = plan.take_profit
                else:
                    # Shouldn't happen with current logic
                    exit_price = candle['close']
                
                # Calculate P&L
                pnl = calculate_pnl_with_costs(
                    plan,
                    exit_price,
                    params
                )
                
                # Calculate realized R
                entry = plan.actual_entry_price or plan.entry_price
                stop = plan.stop_loss
                risk = abs(entry - stop)
                if is_long:
                    realized_r = (exit_price - entry) / risk if risk > 0 else 0
                else:
                    realized_r = (entry - exit_price) / risk if risk > 0 else 0
                
                # Update trade record
                for trade in trades:
                    if (trade['entry_idx'] == plan.filled_at_idx and 
                        trade['symbol'] == symbol and
                        trade['exit_idx'] is None):  # Find the unfilled trade
                        trade['realized_R'] = realized_r
                        trade['exit_time'] = candle.get('timestamp')
                        trade['exit_idx'] = idx
                        trade['exit_reason'] = exit_reason
                        trade['pnl'] = pnl
                        break
                
                # Update capital
                capital += pnl
                
                # Remove from open positions
                open_positions.remove(plan)
            else:
                # No exit, manage trade (update stops if needed)
                management = manage_trade_plan(
                    plan,
                    candle['close'],
                    params
                )
                
                # Update stop if breakeven move triggered
                if management.get("update_stop") is not None:
                    plan.stop_loss = management["update_stop"]
        
        # Look for new setups (simplified - only check fresh zones)
        if idx > 100:  # Need some history for HTF/ITF analysis
            for zone in zones:
                if zone.is_fresh and zone.created_at < idx:
                    # Check if we already have a pending order or position for this zone
                    zone_already_traded = any(
                        p.zone == zone for p in pending_plans + open_positions
                    )
                    if zone_already_traded:
                        continue
                    
                    # Score the zone (simplified - use placeholder curve/trend)
                    score = odds_enhancer_score(
                        zone,
                        candle['close'],
                        CurveLocation.EQUILIBRIUM,  # Simplified
                        TrendDirection.SIDEWAYS,     # Simplified
                        params,
                        None  # opposing_zone
                    )
                    
                    if score >= params.min_setup_score:
                        # Build trade plan
                        plan = build_trade_plan(
                            zone,
                            candle['close'],
                            capital,
                            params,
                            None,  # opposing_zone simplified
                            score
                        )
                        
                        if plan and plan.r_multiple >= params.min_reward_risk:
                            plan.placed_at_idx = idx
                            pending_plans.append(plan)
    
    # Close any remaining open positions at EOD (end of data)
    for plan in open_positions:
        is_long = plan.zone.zone_type == ZoneType.DEMAND
        exit_price = candles[-1]['close']
        
        pnl = calculate_pnl_with_costs(plan, exit_price, params)
        
        entry = plan.actual_entry_price or plan.entry_price
        stop = plan.stop_loss
        risk = abs(entry - stop)
        if is_long:
            realized_r = (exit_price - entry) / risk if risk > 0 else 0
        else:
            realized_r = (entry - exit_price) / risk if risk > 0 else 0
        
        # Update trade record
        for trade in trades:
            if (trade['entry_idx'] == plan.filled_at_idx and 
                trade['symbol'] == symbol and
                trade['exit_idx'] is None):
                trade['realized_R'] = realized_r
                trade['exit_time'] = candles[-1].get('timestamp')
                trade['exit_idx'] = len(candles) - 1
                trade['exit_reason'] = 'EOD_CLOSE'
                trade['pnl'] = pnl
                break
        
        capital += pnl
    
    # Convert zones to dicts for output
    zone_dicts = []
    for zone in zones:
        zone_dicts.append({
            'symbol': symbol,
            'zone_type': zone.zone_type.value,
            'proximal': zone.proximal,
            'distal': zone.distal,
            'created_at': zone.created_at,
            'base_len': zone.base_len,
            'legout_len': zone.legout_len,
            'legout_return': zone.legout_return,
            'freshness_touches': zone.freshness_touches,
            'is_fresh': zone.is_fresh,
        })
    
    return trades, zone_dicts, capital


def load_config(config_path: str) -> Dict[str, Any]:
    """Load experiment configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_git_info() -> Dict[str, str]:
    """Get current git commit hash and branch"""
    try:
        commit_hash = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        
        return {'commit_hash': commit_hash, 'branch': branch}
    except:
        return {'commit_hash': 'unknown', 'branch': 'unknown'}


def create_artifacts_folder() -> Path:
    """Create timestamped artifacts folder
    
    Returns:
        Path to created folder: ./artifacts/sd_v1/<timestamp>_<short_hash>/
    """
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    git_info = get_git_info()
    short_hash = git_info['commit_hash'][:8]
    
    folder_name = f"{timestamp}_{short_hash}"
    artifacts_dir = Path(__file__).parent.parent.parent / 'artifacts' / 'sd_v1' / folder_name
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    return artifacts_dir


def run_backtest_experiment(config_path: str) -> ExperimentResult:
    """Run a complete backtest experiment and generate artifacts
    
    Main entry point for running experiments. Loads config, executes backtests
    across all symbols, validates integrity, and writes artifacts.
    
    Args:
        config_path: Path to YAML configuration file
    
    Returns:
        ExperimentResult with all data and artifacts
    """
    # Load configuration
    config = load_config(config_path)
    
    # Log if this is a futures config (optional validation)
    config_name = config.get('name', Path(config_path).stem)
    if 'futures' in config_name.lower():
        print("=" * 80)
        print("FUTURES/PERPETUAL CONTRACT MODE DETECTED")
        print("=" * 80)
        print(f"Config: {config_name}")
        print("This strategy is designed for futures/perpetual contracts.")
        print("Assumes: Bidirectional trading (LONG/SHORT), leverage, high liquidity.")
        print("=" * 80)
        print()
    
    # Create parameters from config
    params = SupplyDemandParameters(
        boring_body_ratio=config['candle_classification']['boring_body_ratio'],
        exciting_body_ratio=config['candle_classification']['exciting_body_ratio'],
        min_base_candles=config['zone_detection']['min_base_candles'],
        max_base_candles=config['zone_detection']['max_base_candles'],
        min_legout_candles=config['zone_detection']['min_legout_candles'],
        proximal_mode=config['zone_detection']['proximal_mode'],
        min_setup_score=config['scoring']['min_setup_score'],
        freshness_touches_best=config['scoring']['freshness_touches_best'],
        freshness_touches_good=config['scoring']['freshness_touches_good'],
        base_time_best=config['scoring']['base_time_best'],
        base_time_good=config['scoring']['base_time_good'],
        legout_strength_high_threshold=config['scoring']['legout_strength_high_threshold'],
        legout_strength_mid_threshold=config['scoring']['legout_strength_mid_threshold'],
        risk_pct=config['trade_management']['risk_pct'],
        breakeven_at_r=config['trade_management']['breakeven_at_r'],
        take_profit_at_r=config['trade_management']['take_profit_at_r'],
        min_reward_risk=config['trade_management']['min_reward_risk'],
        stop_buffer_pct=config['trade_management']['stop_buffer_pct'],
        pivot_len=config['trend_detection']['pivot_len'],
        pivots_to_consider=config['trend_detection']['pivots_to_consider'],
        allow_eq_trades=config['mtf_gating']['allow_eq_trades'],
        eq_requires_trend_alignment=config['mtf_gating']['eq_requires_trend_alignment'],
        eq_min_setup_score_bonus=config['mtf_gating']['eq_min_setup_score_bonus'],
        entry_mode=EntryMode.LIMIT if config['entry']['entry_mode'] == 'limit' else EntryMode.CONFIRMATION,
        ttl_bars=config['entry']['ttl_bars'],
        fees_bps=config['costs']['fees_bps'],
        slippage_bps=config['costs']['slippage_bps'],
        htf_tf=config['timeframes']['htf'],
        itf_tf=config['timeframes']['itf'],
        ltf_tf=config['timeframes']['ltf'],
        rtf_tf=config['timeframes']['rtf'],
    )
    
    # Run backtests for each symbol
    symbol_results = []
    all_trades = []
    all_zones = []
    
    initial_capital = config['initial_capital']
    
    for symbol in config['symbols']:
        print(f"Running backtest for {symbol}...")
        
        # Generate synthetic candles with symbol-specific seed
        # Use hash of symbol + base seed to ensure different data per symbol
        base_seed = config['data_generation']['seed']
        if base_seed is not None:
            symbol_seed = hash(symbol + str(base_seed)) % (2**31)  # Keep seed in valid range
        else:
            symbol_seed = None
        
        candles = generate_synthetic_candles(
            symbol,
            num_candles=config['data_generation']['num_candles'],
            volatility=config['data_generation']['volatility'],
            seed=symbol_seed
        )
        
        # Execute backtest
        trades, zones, final_capital = execute_backtest_for_symbol(
            symbol,
            candles,
            params,
            initial_capital
        )
        
        # Calculate symbol metrics
        filled_trades = [t for t in trades if t['realized_R'] is not None]
        won_trades = [t for t in filled_trades if t['pnl'] > 0]
        lost_trades = [t for t in filled_trades if t['pnl'] <= 0]
        
        symbol_result = SymbolResult(
            symbol=symbol,
            total_zones=len(zones),
            fresh_zones=len([z for z in zones if z['is_fresh']]),
            trades_placed=len(trades),
            trades_filled=len(filled_trades),
            trades_won=len(won_trades),
            trades_lost=len(lost_trades),
            total_pnl=sum(t['pnl'] for t in filled_trades),
            win_rate=len(won_trades) / len(filled_trades) if filled_trades else 0.0,
            avg_r_realized=sum(t['realized_R'] for t in filled_trades) / len(filled_trades) if filled_trades else 0.0,
            max_drawdown=0.0,  # Simplified for now
            final_capital=final_capital
        )
        
        symbol_results.append(symbol_result)
        all_trades.extend(trades)
        all_zones.extend(zones)
    
    # Guard-rail: Validate that multi-symbol runs have different data per symbol
    if len(config['symbols']) >= 2:
        # Compare results between first two symbols
        if len(symbol_results) >= 2:
            sr1, sr2 = symbol_results[0], symbol_results[1]
            
            # Check if zone counts are identical (unlikely if data differs)
            # Check if trade entry prices are identical (very unlikely if data differs)
            identical_zones = (sr1.total_zones == sr2.total_zones and 
                             sr1.fresh_zones == sr2.fresh_zones)
            
            # Get trades for first two symbols
            trades_sym1 = [t for t in all_trades if t['symbol'] == config['symbols'][0]]
            trades_sym2 = [t for t in all_trades if t['symbol'] == config['symbols'][1]]
            
            # Check if entry prices are suspiciously similar
            if trades_sym1 and trades_sym2 and len(trades_sym1) == len(trades_sym2):
                entries_match = all(
                    abs(t1['entry'] - t2['entry']) < 1e-6 
                    for t1, t2 in zip(trades_sym1, trades_sym2)
                )
                if entries_match and identical_zones:
                    raise ValueError(
                        f"Multi-symbol data isolation failure detected!\n"
                        f"Symbols {config['symbols'][0]} and {config['symbols'][1]} have identical results:\n"
                        f"  - Same zone counts ({sr1.total_zones} zones)\n"
                        f"  - Same number of trades ({len(trades_sym1)} trades)\n"
                        f"  - Identical entry prices\n"
                        f"Likely cause: Same seed or candle data being reused across symbols.\n"
                        f"Check that generate_synthetic_candles is using symbol-specific seeds."
                    )
    
    # Calculate aggregate metrics
    all_filled_trades = [t for t in all_trades if t['realized_R'] is not None]
    all_won_trades = [t for t in all_filled_trades if t['pnl'] > 0]
    
    aggregate_metrics = {
        'total_symbols': len(config['symbols']),
        'total_trades': len(all_trades),
        'total_filled': len(all_filled_trades),
        'total_won': len(all_won_trades),
        'total_lost': len(all_filled_trades) - len(all_won_trades),
        'overall_win_rate': len(all_won_trades) / len(all_filled_trades) if all_filled_trades else 0.0,
        'overall_pnl': sum(t['pnl'] for t in all_filled_trades),
        'avg_r_realized': sum(t['realized_R'] for t in all_filled_trades) / len(all_filled_trades) if all_filled_trades else 0.0,
    }
    
    # Run integrity checks
    violations = []
    for trade in all_trades:
        if trade['realized_R'] is not None:
            # Check minimum R
            violation = validate_minimum_r(
                trade,
                params.min_reward_risk
            )
            if violation:
                violations.append(violation)
            
            # Check entry after zone creation
            violation = validate_entry_after_zone_creation(
                trade,
                trade['zone_created_at'],
                None,
                trade['entry_idx'],
                trade.get('entry_time')
            )
            if violation:
                violations.append(violation)
    
    violation_counts = {}
    for v in violations:
        violation_counts[v.violation_type] = violation_counts.get(v.violation_type, 0) + 1
    
    integrity_report = IntegrityReport(
        total_trades=len(all_filled_trades),
        violations=violations,
        violation_counts=violation_counts,
        clean=len(violations) == 0
    )
    
    # Create run manifest
    git_info = get_git_info()
    run_manifest = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'git_commit': git_info['commit_hash'],
        'git_branch': git_info['branch'],
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'config_file': config_path,
        'config_hash': hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest(),
    }
    
    return ExperimentResult(
        config=config,
        symbol_results=symbol_results,
        all_trades=all_trades,
        all_zones=all_zones,
        aggregate_metrics=aggregate_metrics,
        integrity_report=integrity_report,
        run_manifest=run_manifest
    )


def write_artifacts(result: ExperimentResult, artifacts_dir: Path):
    """Write all artifacts to disk
    
    Args:
        result: ExperimentResult to write
        artifacts_dir: Directory to write artifacts to
    """
    # Write summary.json
    summary = {
        'aggregate_metrics': result.aggregate_metrics,
        'symbol_results': [asdict(sr) for sr in result.symbol_results],
    }
    with open(artifacts_dir / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Write trades.csv (always create file, even if empty)
    trades_file = artifacts_dir / 'trades.csv'
    with open(trades_file, 'w', newline='') as f:
        if result.all_trades:
            # Get all possible fieldnames
            fieldnames = set()
            for trade in result.all_trades:
                fieldnames.update(trade.keys())
            fieldnames = sorted(fieldnames)
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.all_trades)
        else:
            # Write header only with expected columns
            expected_columns = [
                'symbol', 'side', 'entry', 'stop', 'target',
                'planned_R', 'planned_r', 'realized_R', 
                'entry_time', 'entry_idx', 'exit_time', 'exit_idx',
                'exit_reason', 'score', 'zone_created_at', 'pnl', 'position_size'
            ]
            writer = csv.DictWriter(f, fieldnames=expected_columns)
            writer.writeheader()
    
    # Write zones.csv
    if result.all_zones:
        zones_file = artifacts_dir / 'zones.csv'
        with open(zones_file, 'w', newline='') as f:
            fieldnames = sorted(result.all_zones[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.all_zones)
    
    # Write run_manifest.json
    with open(artifacts_dir / 'run_manifest.json', 'w') as f:
        json.dump(result.run_manifest, f, indent=2)
    
    # Write violations.json
    # Helper to convert datetime to string for JSON serialization
    def serialize_for_json(obj):
        """Convert non-serializable objects to JSON-compatible format"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [serialize_for_json(item) for item in obj]
        return obj
    
    violations_data = {
        'total_trades': result.integrity_report.total_trades,
        'clean': result.integrity_report.clean,
        'violation_counts': {k.value: v for k, v in result.integrity_report.violation_counts.items()},
        'violations': [
            {
                'type': v.violation_type.value,
                'reason': v.reason,
                'details': serialize_for_json(v.details),
                'trade': serialize_for_json(v.trade)
            }
            for v in result.integrity_report.violations
        ]
    }
    with open(artifacts_dir / 'violations.json', 'w') as f:
        json.dump(violations_data, f, indent=2)
    
    print(f"\nArtifacts written to: {artifacts_dir}")
    print(f"  - summary.json ({len(result.symbol_results)} symbols)")
    print(f"  - trades.csv ({len(result.all_trades)} trades)")
    print(f"  - zones.csv ({len(result.all_zones)} zones)")
    print(f"  - run_manifest.json")
    print(f"  - violations.json ({len(result.integrity_report.violations)} violations)")


if __name__ == "__main__":
    # Simple test
    import sys
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        result = run_backtest_experiment(config_path)
        artifacts_dir = create_artifacts_folder()
        write_artifacts(result, artifacts_dir)
    else:
        print("Usage: python runner.py <config_path>")
