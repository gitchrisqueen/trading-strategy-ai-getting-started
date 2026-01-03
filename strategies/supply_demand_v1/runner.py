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
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

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

from strategies.supply_demand_v1.data_loader import (
    load_historical_candles,
    find_common_window,
    HistoricalDataError,
)


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown from an equity curve
    
    Args:
        equity_curve: List of equity values over time
    
    Returns:
        Maximum drawdown as a positive number (0.0 if no drawdown)
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    
    max_drawdown = 0.0
    peak = equity_curve[0]
    
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return max_drawdown


def calculate_candle_checksum(candles: List[Dict[str, Any]]) -> str:
    """Calculate checksum/hash of close prices for data verification
    
    Args:
        candles: List of OHLC candles
    
    Returns:
        MD5 hash of close prices as hex string
    """
    if not candles:
        return ""
    
    close_prices = [str(c['close']) for c in candles]
    close_string = ','.join(close_prices)
    return hashlib.md5(close_string.encode()).hexdigest()


def check_metrics_consistency(
    symbol_results: List['SymbolResult'],
    all_trades: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Check for impossible or likely-bug metric situations
    
    Args:
        symbol_results: Per-symbol backtest results
        all_trades: All trades from backtest
    
    Returns:
        List of warning dictionaries
    """
    warnings = []
    
    for sr in symbol_results:
        # Warning 1: max_drawdown == 0.0 while trades_filled > 0
        if sr.max_drawdown == 0.0 and sr.trades_filled > 0:
            warnings.append({
                'type': 'zero_drawdown_with_trades',
                'severity': 'warning',
                'symbol': sr.symbol,
                'message': f"Symbol {sr.symbol} has {sr.trades_filled} filled trades but max_drawdown is 0.0. This is unlikely unless all trades were profitable.",
                'details': {
                    'trades_filled': sr.trades_filled,
                    'max_drawdown': sr.max_drawdown,
                    'total_pnl': sr.total_pnl,
                }
            })
        
        # Warning 2: abs(avg_r_realized) < 0.02 while abs(total_pnl) is large
        # Define "large" as > 5% of a typical initial capital (e.g., $10k -> $500)
        large_pnl_threshold = 500.0
        if sr.trades_filled > 0 and abs(sr.avg_r_realized) < 0.02 and abs(sr.total_pnl) > large_pnl_threshold:
            warnings.append({
                'type': 'low_r_with_large_pnl',
                'severity': 'warning',
                'symbol': sr.symbol,
                'message': f"Symbol {sr.symbol} has large P&L (${sr.total_pnl:.2f}) but avg R realized is near zero ({sr.avg_r_realized:.2f}R). Check R calculation or position sizing.",
                'details': {
                    'avg_r_realized': sr.avg_r_realized,
                    'total_pnl': sr.total_pnl,
                    'trades_filled': sr.trades_filled,
                }
            })
    
    return warnings


@dataclass
class DecisionFunnel:
    """Decision funnel metrics for tracking why trades were/weren't taken"""
    symbol: str
    zones_detected: int = 0
    zones_fresh: int = 0
    candidates_evaluated: int = 0
    rejected_curve: int = 0
    rejected_trend: int = 0
    rejected_min_score: int = 0
    rejected_min_rr: int = 0
    orders_placed: int = 0
    orders_filled: int = 0
    orders_expired_ttl: int = 0


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
    equity_curve: List[float]  # Track full equity curve
    # Data provenance
    data_provenance: Dict[str, Any]  # first/last timestamp, close prices, checksum, etc.
    # Decision funnel
    decision_funnel: Optional['DecisionFunnel'] = None


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
    metrics_warnings: List[Dict[str, Any]]  # Consistency warnings
    decision_funnels: List[DecisionFunnel]  # Per-symbol decision funnels


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


def load_candles_from_config(
    symbol: str,
    config: Dict[str, Any],
    return_metadata: bool = False
) -> Any:
    """Load candles based on config (synthetic or historical)
    
    Args:
        symbol: Trading symbol
        config: Experiment configuration
        return_metadata: If True, return (candles, metadata) tuple
    
    Returns:
        If return_metadata=False: List of candle dictionaries
        If return_metadata=True: Tuple of (candles, metadata_dict)
    
    Raises:
        HistoricalDataError: If historical data requested but unavailable
        ValueError: If data_source is invalid
    """
    data_source = config.get('data_source', 'synthetic')
    
    if data_source == 'synthetic':
        # Generate synthetic candles
        base_seed = config['data_generation']['seed']
        if base_seed is not None:
            symbol_seed = hash(symbol + str(base_seed)) % (2**31)
        else:
            symbol_seed = None
        
        candles = generate_synthetic_candles(
            symbol,
            num_candles=config['data_generation']['num_candles'],
            volatility=config['data_generation']['volatility'],
            seed=symbol_seed
        )
        
        if return_metadata:
            # For synthetic data, create basic metadata
            metadata = {
                'available_count': len(candles),
                'used_count': len(candles),
                'available_first_ts': candles[0]['timestamp'].isoformat() if candles else None,
                'available_last_ts': candles[-1]['timestamp'].isoformat() if candles else None,
                'used_first_ts': candles[0]['timestamp'].isoformat() if candles else None,
                'used_last_ts': candles[-1]['timestamp'].isoformat() if candles else None,
            }
            return candles, metadata
        
        return candles
        
    elif data_source == 'historical':
        # Load historical candles
        if 'historical_data' not in config:
            raise ValueError(
                "data_source is 'historical' but 'historical_data' section is missing in config. "
                "Please add 'historical_data' with exchange, market_type, and data_dir fields."
            )
        
        hist_config = config['historical_data']
        exchange = hist_config.get('exchange', 'binance')
        market_type = hist_config.get('market_type', 'futures')
        data_dir = Path(hist_config.get('data_dir', './data'))
        
        # Get timeframe and date range
        timeframe = config['timeframes']['ltf']  # Use LTF as primary timeframe
        
        # Check if use_full_history is enabled
        use_full_history = config.get('use_full_history', False)
        
        if use_full_history:
            # Find common window across all required timeframes
            required_tfs = [config['timeframes']['ltf']]
            if config['timeframes'].get('htf'):
                required_tfs.append(config['timeframes']['htf'])
            if config['timeframes'].get('itf'):
                required_tfs.append(config['timeframes']['itf'])
            
            try:
                start_date, end_date = find_common_window(
                    symbol=symbol,
                    timeframes=required_tfs,
                    data_dir=data_dir,
                    exchange=exchange,
                    market_type=market_type
                )
                
                if not start_date or not end_date:
                    raise HistoricalDataError(
                        f"No common time window found for {symbol} across timeframes {required_tfs}"
                    )
                
                print(f"  Using full history for {symbol}: {start_date} to {end_date}")
                
            except HistoricalDataError as e:
                raise HistoricalDataError(
                    f"Failed to determine full history window for {symbol}: {e}"
                )
        else:
            # Use explicit start/end dates from config
            start_date = config.get('start_date', '2024-01-01')
            end_date = config.get('end_date', '2024-03-31')
        
        try:
            if return_metadata:
                candles, metadata = load_historical_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    data_dir=data_dir,
                    exchange=exchange,
                    market_type=market_type,
                    return_metadata=True
                )
                return candles, metadata
            else:
                candles = load_historical_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    data_dir=data_dir,
                    exchange=exchange,
                    market_type=market_type,
                    return_metadata=False
                )
                return candles
        except HistoricalDataError as e:
            # Re-raise with more context
            raise HistoricalDataError(
                f"Failed to load historical data for {symbol}:\n{e}\n\n"
                f"Config settings:\n"
                f"  - data_source: {data_source}\n"
                f"  - exchange: {exchange}\n"
                f"  - market_type: {market_type}\n"
                f"  - timeframe: {timeframe}\n"
                f"  - date_range: {start_date} to {end_date}\n"
                f"  - data_dir: {data_dir}\n"
                f"  - use_full_history: {use_full_history}\n"
            )
    
    else:
        raise ValueError(
            f"Invalid data_source: '{data_source}'. "
            f"Must be 'synthetic' or 'historical'."
        )



def execute_backtest_for_symbol(
    symbol: str,
    candles: List[Dict[str, Any]],
    params: SupplyDemandParameters,
    initial_capital: float
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, List[float], DecisionFunnel]:
    """Execute backtest for a single symbol
    
    Args:
        symbol: Trading pair symbol
        candles: OHLC candle data
        params: Strategy parameters
        initial_capital: Starting capital
    
    Returns:
        Tuple of (trades, zones, final_capital, equity_curve, decision_funnel)
    """
    # Optional profiling support
    import os
    enable_profiling = os.environ.get('SDV1_PROFILE') == '1'
    
    if enable_profiling:
        import time
        stage_timings = {}
        stage_start = time.time()
    
    # Detect all zones
    zones = detect_zones_dbr_rbd(candles, params)
    
    if enable_profiling:
        stage_timings['zone_detection'] = time.time() - stage_start
        stage_start = time.time()
    
    # OPTIMIZATION: Precompute zone freshness using vectorized operations
    # This eliminates the need to check each zone on every candle (O(Z*C) -> O(Z+C))
    from strategies.supply_demand_v1.zone_freshness_precompute import (
        precompute_zone_freshness,
        is_zone_fresh_at_idx,
        build_zone_creation_index,
        cache_zone_metrics
    )
    
    precompute_zone_freshness(zones, candles)
    zone_creation_index = build_zone_creation_index(zones)
    cache_zone_metrics(zones)
    
    if enable_profiling:
        stage_timings['freshness_precompute'] = time.time() - stage_start
        stage_start = time.time()
    
    # Initialize decision funnel tracking
    funnel = DecisionFunnel(symbol=symbol)
    funnel.zones_detected = len(zones)
    # Count zones that are fresh at the start (index 0)
    funnel.zones_fresh = len([z for z in zones if z.first_touch_idx is None or z.first_touch_idx > 0])
    
    # Track capital and positions
    capital = initial_capital
    trades = []
    pending_plans = []  # Plans with pending orders
    open_positions = []  # Plans with filled orders (active positions)
    
    # Track equity curve for drawdown calculation
    equity_curve = [initial_capital]  # Start with initial capital
    
    # Simulate backtest bar by bar
    for idx in range(len(candles)):
        candle = candles[idx]
        
        # Zone freshness is already precomputed - no per-candle checks needed!
        
        # Check for fills on pending orders
        for plan in list(pending_plans):
            if plan.order_state == OrderState.PENDING:
                # Check TTL expiration first
                if params.ttl_bars and (idx - plan.placed_at_idx) >= params.ttl_bars:
                    plan.order_state = OrderState.CANCELLED
                    pending_plans.remove(plan)
                    funnel.orders_expired_ttl += 1
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
                    funnel.orders_filled += 1
                    
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
                equity_curve.append(capital)
                
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
        
        # Look for new setups - only check zones that are fresh at this index
        if idx > 100:  # Need some history for HTF/ITF analysis
            # OPTIMIZATION: Only evaluate zones that are:
            # 1. Created before this index
            # 2. Fresh at this index (using precomputed first_touch_idx)
            for zone in zones:
                if zone.created_at >= idx:
                    continue  # Zone not created yet
                
                # Check freshness using precomputed index (O(1) instead of O(C))
                if not is_zone_fresh_at_idx(zone, idx):
                    continue  # Zone already touched
                
                # Check if we already have a pending order or position for this zone
                zone_already_traded = any(
                    p.zone == zone for p in pending_plans + open_positions
                )
                if zone_already_traded:
                    continue
                
                # Candidate evaluation
                funnel.candidates_evaluated += 1
                
                # Score the zone (simplified - use placeholder curve/trend)
                # Note: In full implementation, curve and trend rejection would be tracked here
                score = odds_enhancer_score(
                    zone,
                    candle['close'],
                    CurveLocation.EQUILIBRIUM,  # Simplified
                    TrendDirection.SIDEWAYS,     # Simplified
                    params,
                    None  # opposing_zone
                )
                
                if score < params.min_setup_score:
                    funnel.rejected_min_score += 1
                    continue
                
                # Build trade plan
                plan = build_trade_plan(
                    zone,
                    candle['close'],
                    capital,
                    params,
                    None,  # opposing_zone simplified
                    score
                )
                
                if not plan or plan.r_multiple < params.min_reward_risk:
                    funnel.rejected_min_rr += 1
                    continue
                
                # Place order
                plan.placed_at_idx = idx
                pending_plans.append(plan)
                funnel.orders_placed += 1
    
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
        equity_curve.append(capital)
    
    if enable_profiling:
        stage_timings['backtest_loop'] = time.time() - stage_start
        stage_start = time.time()
    
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
    
    if enable_profiling:
        stage_timings['output_conversion'] = time.time() - stage_start
        
        # Print profiling results
        print("\n" + "=" * 80)
        print(f"PROFILING RESULTS - {symbol}")
        print("=" * 80)
        total_time = sum(stage_timings.values())
        for stage, timing in stage_timings.items():
            pct = (timing / total_time * 100) if total_time > 0 else 0
            print(f"{stage:25s}: {timing:7.3f}s ({pct:5.1f}%)")
        print(f"{'TOTAL':25s}: {total_time:7.3f}s")
        print("=" * 80 + "\n")
    
    return trades, zone_dicts, capital, equity_curve, funnel


def run_symbol_backtest(
    symbol: str,
    config: Dict[str, Any],
    params: SupplyDemandParameters,
    initial_capital: float
) -> SymbolResult:
    """Pure function to run backtest for a single symbol.
    
    This function is designed for parallel execution:
    - No side effects (no file I/O, no shared state modification)
    - Loads its own data (no large shared DataFrames passed via pickle)
    - Returns complete SymbolResult with all trades, zones, metrics
    
    Args:
        symbol: Trading pair symbol
        config: Full experiment configuration
        params: Strategy parameters
        initial_capital: Starting capital
    
    Returns:
        SymbolResult containing all backtest data for this symbol
    
    Raises:
        Exception: Any error during backtest execution
    """
    try:
        # Load candles with metadata (each worker loads its own data)
        candles, metadata = load_candles_from_config(symbol, config, return_metadata=True)
        
        # Execute backtest
        trades, zones, final_capital, equity_curve, funnel = execute_backtest_for_symbol(
            symbol,
            candles,
            params,
            initial_capital
        )
        
        # Calculate max drawdown
        max_drawdown = calculate_max_drawdown(equity_curve)
        
        # Build data provenance
        data_provenance = {
            'first_timestamp': candles[0]['timestamp'].isoformat() if candles else None,
            'last_timestamp': candles[-1]['timestamp'].isoformat() if candles else None,
            'first_close': candles[0]['close'] if candles else None,
            'last_close': candles[-1]['close'] if candles else None,
            'candle_count': len(candles),
            'checksum': calculate_candle_checksum(candles),
            'available_first_ts': metadata.get('available_first_ts'),
            'available_last_ts': metadata.get('available_last_ts'),
            'available_count': metadata.get('available_count'),
            'used_first_ts': metadata.get('used_first_ts'),
            'used_last_ts': metadata.get('used_last_ts'),
            'used_count': metadata.get('used_count'),
        }
        
        # Calculate metrics
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
            max_drawdown=max_drawdown,
            final_capital=final_capital,
            equity_curve=equity_curve,
            data_provenance=data_provenance,
            decision_funnel=funnel,
        )
        
        # Store trades and zones on the result for later aggregation
        # We need to attach them as attributes for collection
        symbol_result.trades = trades
        symbol_result.zones = zones
        
        return symbol_result
        
    except Exception as e:
        # Return a failure result with error information
        # This allows the parent to continue with other symbols
        error_result = SymbolResult(
            symbol=symbol,
            total_zones=0,
            fresh_zones=0,
            trades_placed=0,
            trades_filled=0,
            trades_won=0,
            trades_lost=0,
            total_pnl=0.0,
            win_rate=0.0,
            avg_r_realized=0.0,
            max_drawdown=0.0,
            final_capital=initial_capital,
            equity_curve=[initial_capital],
            data_provenance={
                'error': str(e),
                'error_type': type(e).__name__
            },
            decision_funnel=DecisionFunnel(symbol=symbol),
        )
        error_result.trades = []
        error_result.zones = []
        error_result.error = str(e)
        return error_result


def run_chunk(
    chunk_symbols: List[str],
    config: Dict[str, Any],
    params: SupplyDemandParameters,
    initial_capital: float
) -> List[SymbolResult]:
    """Run backtest for a chunk of symbols sequentially.
    
    This function is executed in a worker process. It processes
    multiple symbols to reduce per-process startup overhead.
    
    Args:
        chunk_symbols: List of symbols to process
        config: Full experiment configuration
        params: Strategy parameters
        initial_capital: Starting capital
    
    Returns:
        List of SymbolResults
    """
    results = []
    for symbol in chunk_symbols:
        result = run_symbol_backtest(symbol, config, params, initial_capital)
        results.append(result)
    return results


def run_backtests_parallel(
    symbols: List[str],
    config: Dict[str, Any],
    params: SupplyDemandParameters,
    initial_capital: float,
    parallel_config: Dict[str, Any]
) -> List[SymbolResult]:
    """Run backtests for multiple symbols in parallel using ProcessPoolExecutor.
    
    Args:
        symbols: List of symbols to backtest
        config: Full experiment configuration
        params: Strategy parameters
        initial_capital: Starting capital
        parallel_config: Parallel execution configuration with keys:
            - workers: Number of worker processes
            - chunk_size: Number of symbols per chunk
            - fail_fast: If True, stop on first failure
    
    Returns:
        List of SymbolResults (sorted by symbol for determinism)
    """
    workers = parallel_config.get('workers', max(1, os.cpu_count() - 1))
    chunk_size = parallel_config.get('chunk_size', 2)
    fail_fast = parallel_config.get('fail_fast', True)
    
    # Split symbols into chunks
    chunks = [symbols[i:i+chunk_size] for i in range(0, len(symbols), chunk_size)]
    
    print(f"Running parallel backtest:")
    print(f"  - Workers: {workers}")
    print(f"  - Total symbols: {len(symbols)}")
    print(f"  - Chunks: {len(chunks)} (chunk_size={chunk_size})")
    print(f"  - Fail fast: {fail_fast}")
    print()
    
    all_results = []
    errors = []
    
    # Use ProcessPoolExecutor for parallel execution
    # Note: On some platforms, use 'spawn' method for better compatibility
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit all chunks
        future_to_chunk = {
            executor.submit(run_chunk, chunk, config, params, initial_capital): chunk
            for chunk in chunks
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_chunk):
            chunk = future_to_chunk[future]
            try:
                chunk_results = future.result()
                all_results.extend(chunk_results)
                
                # Check for errors in results
                for result in chunk_results:
                    if hasattr(result, 'error'):
                        error_msg = f"Symbol {result.symbol} failed: {result.error}"
                        errors.append(error_msg)
                        if fail_fast:
                            print(f"ERROR: {error_msg}")
                            executor.shutdown(wait=False, cancel_futures=True)
                            raise RuntimeError(f"Backtest failed for {result.symbol}: {result.error}")
                
                # Progress update
                completed_symbols = [r.symbol for r in chunk_results]
                print(f"  ✓ Completed chunk: {', '.join(completed_symbols)}")
                
            except Exception as e:
                error_msg = f"Chunk {chunk} failed: {e}"
                errors.append(error_msg)
                if fail_fast:
                    print(f"ERROR: {error_msg}")
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                else:
                    print(f"WARNING: {error_msg}")
    
    # Sort results by symbol for determinism
    all_results.sort(key=lambda r: r.symbol)
    
    # Print error summary if any
    if errors and not fail_fast:
        print("\n" + "=" * 80)
        print("ERRORS DURING PARALLEL EXECUTION")
        print("=" * 80)
        for error in errors:
            print(f"  - {error}")
        print("=" * 80)
    
    return all_results


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
    
    # Check if parallel execution is enabled
    parallel_config = config.get('parallel', {})
    parallel_enabled = parallel_config.get('enabled', False)
    
    initial_capital = config['initial_capital']
    
    # Run backtests (parallel or serial based on config)
    if parallel_enabled:
        print("=" * 80)
        print("PARALLEL EXECUTION MODE")
        print("=" * 80)
        
        # Extract parallel settings
        workers = parallel_config.get('workers', max(1, os.cpu_count() - 1))
        chunk_size = parallel_config.get('chunk_size', 2)
        fail_fast = parallel_config.get('fail_fast', True)
        
        parallel_settings = {
            'workers': workers,
            'chunk_size': chunk_size,
            'fail_fast': fail_fast,
        }
        
        # Run parallel
        symbol_results = run_backtests_parallel(
            config['symbols'],
            config,
            params,
            initial_capital,
            parallel_settings
        )
        
    else:
        print("Running backtests serially...")
        symbol_results = []
        
        for symbol in config['symbols']:
            print(f"Running backtest for {symbol}...")
            result = run_symbol_backtest(symbol, config, params, initial_capital)
            symbol_results.append(result)
    
    # Aggregate results (sort by symbol for determinism)
    symbol_results.sort(key=lambda r: r.symbol)
    
    # Extract trades and zones from results
    all_trades = []
    all_zones = []
    decision_funnels = []
    
    # Collect window metadata for reporting
    used_window_global_start = None
    used_window_global_end = None
    
    for result in symbol_results:
        # Extract trades and zones (attached by run_symbol_backtest)
        if hasattr(result, 'trades'):
            all_trades.extend(result.trades)
        if hasattr(result, 'zones'):
            all_zones.extend(result.zones)
        
        decision_funnels.append(result.decision_funnel)
        
        # Track global window (intersection across all symbols)
        if result.data_provenance.get('used_first_ts'):
            used_ts = datetime.fromisoformat(result.data_provenance['used_first_ts'])
            if not used_window_global_start or used_ts > used_window_global_start:
                used_window_global_start = used_ts
        if result.data_provenance.get('used_last_ts'):
            used_ts = datetime.fromisoformat(result.data_provenance['used_last_ts'])
            if not used_window_global_end or used_ts < used_window_global_end:
                used_window_global_end = used_ts
    
    # Sort trades and zones for determinism
    # Sort trades by (symbol, entry_idx)
    all_trades.sort(key=lambda t: (t['symbol'], t.get('entry_idx', 0)))
    
    # Sort zones by (symbol, created_at)
    all_zones.sort(key=lambda z: (z['symbol'], z.get('created_at', 0)))
    
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
        'accounting_mode': 'per_symbol_independent',  # Each symbol backtested independently
        'total_symbols': len(config['symbols']),
        'total_trades': len(all_trades),
        'total_filled': len(all_filled_trades),
        'total_won': len(all_won_trades),
        'total_lost': len(all_filled_trades) - len(all_won_trades),
        'overall_win_rate': len(all_won_trades) / len(all_filled_trades) if all_filled_trades else 0.0,
        'sum_of_symbol_pnls': sum(t['pnl'] for t in all_filled_trades),  # Renamed from overall_pnl
        'overall_pnl': sum(t['pnl'] for t in all_filled_trades),  # Keep for backward compatibility
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
    
    # Check metrics consistency and add window warnings
    metrics_warnings = check_metrics_consistency(symbol_results, all_trades)
    
    # Check for window utilization warnings (used < 80% of available)
    for sr in symbol_results:
        if sr.data_provenance.get('available_count') and sr.data_provenance.get('used_count'):
            available = sr.data_provenance['available_count']
            used = sr.data_provenance['used_count']
            if available > 0 and used < 0.8 * available:
                metrics_warnings.append({
                    'type': 'low_window_utilization',
                    'severity': 'info',
                    'symbol': sr.symbol,
                    'message': f"Symbol {sr.symbol} used only {used}/{available} candles ({used/available:.1%}). Consider use_full_history=true to use more data.",
                    'details': {
                        'available_count': available,
                        'used_count': used,
                        'utilization_pct': used / available,
                    }
                })
    
    # Create run manifest with enhanced data provenance
    git_info = get_git_info()
    
    # Collect per-symbol data provenance
    symbol_data_provenance = {}
    for sr in symbol_results:
        symbol_data_provenance[sr.symbol] = sr.data_provenance
    
    # Determine data source fields based on config
    data_source = config.get('data_source', 'synthetic')
    
    if data_source == 'synthetic':
        datasource_name = 'synthetic'
        is_synthetic_data = True
        exchange = None
        market_type = None
        data_generation_info = {
            'generator_module': 'strategies.supply_demand_v1.runner.generate_synthetic_candles',
            'base_seed': config['data_generation']['seed'],
            'num_candles': config['data_generation']['num_candles'],
            'volatility': config['data_generation']['volatility'],
        }
    else:  # historical
        hist_config = config.get('historical_data', {})
        exchange = hist_config.get('exchange', 'binance')
        market_type = hist_config.get('market_type', 'futures')
        datasource_name = f"{exchange}_{market_type}"
        is_synthetic_data = False
        data_generation_info = None
    
    # Build requested_window and used_window_global
    requested_window = {
        'start_date': config.get('start_date'),
        'end_date': config.get('end_date'),
        'use_full_history': config.get('use_full_history', False),
    }
    
    used_window_global = {}
    if used_window_global_start and used_window_global_end:
        used_window_global = {
            'start_ts': used_window_global_start.isoformat(),
            'end_ts': used_window_global_end.isoformat(),
        }
    
    run_manifest = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'git_commit': git_info['commit_hash'],
        'git_branch': git_info['branch'],
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'config_file': config_path,
        'config_hash': hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        # Window provenance
        'requested_window': requested_window,
        'used_window_global': used_window_global,
        # Data provenance fields
        'data_source': data_source,
        'datasource_name': datasource_name,
        'is_synthetic_data': is_synthetic_data,
        'exchange': exchange,
        'market_type': market_type,
        'candle_timeframe': params.ltf_tf,  # Primary timeframe for zone detection
        'symbol_data_provenance': symbol_data_provenance,
    }
    
    # Add data_generation info for synthetic data
    if data_generation_info:
        run_manifest['data_generation'] = data_generation_info
    
    return ExperimentResult(
        config=config,
        symbol_results=symbol_results,
        all_trades=all_trades,
        all_zones=all_zones,
        aggregate_metrics=aggregate_metrics,
        integrity_report=integrity_report,
        run_manifest=run_manifest,
        metrics_warnings=metrics_warnings,
        decision_funnels=decision_funnels,
    )


def write_artifacts(result: ExperimentResult, artifacts_dir: Path):
    """Write all artifacts to disk
    
    Args:
        result: ExperimentResult to write
        artifacts_dir: Directory to write artifacts to
    """
    # Write summary.json
    # Convert symbol results to dict but exclude equity_curve (too large for JSON)
    symbol_results_for_json = []
    for sr in result.symbol_results:
        sr_dict = asdict(sr)
        sr_dict.pop('equity_curve', None)  # Remove equity curve from JSON output
        symbol_results_for_json.append(sr_dict)
    
    summary = {
        'aggregate_metrics': result.aggregate_metrics,
        'symbol_results': symbol_results_for_json,
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
    
    # Write metrics_warnings.json
    metrics_warnings_data = {
        'total_warnings': len(result.metrics_warnings),
        'warnings': result.metrics_warnings,
    }
    with open(artifacts_dir / 'metrics_warnings.json', 'w') as f:
        json.dump(metrics_warnings_data, f, indent=2)
    
    # Write decision_funnel.json
    funnel_data = {
        'per_symbol': [asdict(f) for f in result.decision_funnels],
        'aggregate': {
            'zones_detected': sum(f.zones_detected for f in result.decision_funnels),
            'zones_fresh': sum(f.zones_fresh for f in result.decision_funnels),
            'candidates_evaluated': sum(f.candidates_evaluated for f in result.decision_funnels),
            'rejected_curve': sum(f.rejected_curve for f in result.decision_funnels),
            'rejected_trend': sum(f.rejected_trend for f in result.decision_funnels),
            'rejected_min_score': sum(f.rejected_min_score for f in result.decision_funnels),
            'rejected_min_rr': sum(f.rejected_min_rr for f in result.decision_funnels),
            'orders_placed': sum(f.orders_placed for f in result.decision_funnels),
            'orders_filled': sum(f.orders_filled for f in result.decision_funnels),
            'orders_expired_ttl': sum(f.orders_expired_ttl for f in result.decision_funnels),
        }
    }
    with open(artifacts_dir / 'decision_funnel.json', 'w') as f:
        json.dump(funnel_data, f, indent=2)
    
    # Print compact decision funnel table
    print("\n" + "=" * 80)
    print("DECISION FUNNEL")
    print("=" * 80)
    agg = funnel_data['aggregate']
    print(f"Zones Detected:        {agg['zones_detected']}")
    print(f"  └─ Fresh:            {agg['zones_fresh']}")
    print(f"Candidates Evaluated:  {agg['candidates_evaluated']}")
    if agg['rejected_curve'] > 0:
        print(f"  ├─ Rejected (Curve): {agg['rejected_curve']}")
    if agg['rejected_trend'] > 0:
        print(f"  ├─ Rejected (Trend): {agg['rejected_trend']}")
    if agg['rejected_min_score'] > 0:
        print(f"  ├─ Rejected (Score): {agg['rejected_min_score']}")
    if agg['rejected_min_rr'] > 0:
        print(f"  └─ Rejected (Min R): {agg['rejected_min_rr']}")
    print(f"Orders Placed:         {agg['orders_placed']}")
    print(f"  ├─ Filled:           {agg['orders_filled']}")
    print(f"  └─ Expired (TTL):    {agg['orders_expired_ttl']}")
    print("=" * 80)
    
    print(f"\nArtifacts written to: {artifacts_dir}")
    print(f"  - summary.json ({len(result.symbol_results)} symbols)")
    print(f"  - trades.csv ({len(result.all_trades)} trades)")
    print(f"  - zones.csv ({len(result.all_zones)} zones)")
    print(f"  - run_manifest.json")
    print(f"  - violations.json ({len(result.integrity_report.violations)} violations)")
    print(f"  - metrics_warnings.json ({len(result.metrics_warnings)} warnings)")
    print(f"  - decision_funnel.json")


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
