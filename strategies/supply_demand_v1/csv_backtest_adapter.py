"""Supply & Demand V1 CSV Backtest Adapter

This module provides a CSV-based backtesting adapter for the Supply & Demand V1 strategy.
It orchestrates the complete backtest loop including:
- Order fill simulation
- TTL (Time To Live) expiration tracking  
- Position lifecycle management
- PnL calculation with costs
- Artifact generation for PR comparisons

This adapter preserves the existing CSV-based experiment workflow and serves as the
"gold standard" for reproducible experiments. It is separate from the upstream-compatible
adapter (decide_trades_adapter.py) which integrates with the TradingStrategy.ai framework.

Key Functions:
    - run_backtest_experiment: Main entry point for running experiments
    - generate_synthetic_candles_mtf: Create multi-timeframe synthetic OHLC data
    - execute_backtest_for_symbol: Run strategy on a single symbol (core backtest loop)
    - run_backtests_parallel: Execute multiple symbols in parallel
    - write_artifacts: Generate machine-readable artifacts

Artifacts Generated:
    - summary.json: Aggregate metrics + per-symbol breakdown
    - trades.csv: All trades with full details
    - zones.csv: All zones detected with scoring info
    - orders.csv: All order lifecycle events
    - run_manifest.json: Metadata about the run (git commit, config, etc.)
    - violations.json: Integrity check results
    - metrics_warnings.json: Metric validation warnings
    - decision_funnel.json: Decision funnel metrics

Usage:
    This adapter is used by scripts/run_supply_demand_v1.py and should remain
    backward-compatible with existing experiment configs.
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
    check_polarity_flip,
    get_zone_polarity_at_idx,
    check_rtf_refinement,
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

import bisect


# ============================================================================
# Utility Functions
# ============================================================================

def enum_to_string(enum_value: Any) -> str:
    """Convert enum value to string, handling both enum types and plain strings
    
    Args:
        enum_value: Either an enum (with .value attribute) or a string
    
    Returns:
        String representation of the value
    """
    if hasattr(enum_value, 'value'):
        return enum_value.value
    return str(enum_value)


def make_zone_id(symbol: str, zone: Zone) -> str:
    """Create a stable, unique identifier for a zone
    
    Uses immutable fields that define a zone uniquely:
    - symbol: Trading pair
    - created_at: Index where zone was created
    - zone_type: SUPPLY or DEMAND
    - proximal: Entry reference price
    - distal: Stop reference price
    
    Args:
        symbol: Trading pair symbol
        zone: Zone object
    
    Returns:
        Unique string identifier for the zone
    
    Example:
        "BTCUSDT_1234_demand_100.5_99.0"
    """
    zone_type_str = zone.zone_type.value if hasattr(zone.zone_type, 'value') else str(zone.zone_type)
    return f"{symbol}_{zone.created_at}_{zone_type_str}_{zone.proximal}_{zone.distal}"


def validate_timeframe_hierarchy(ltf_tf: str, rtf_tf: Optional[str]) -> None:
    """Validate that RTF is a lower timeframe than LTF
    
    RTF (Refining TimeFrame) must be LOWER (smaller interval) than LTF (Lower TimeFrame).
    This ensures that RTF provides finer-grained price action for entry refinement.
    
    Args:
        ltf_tf: Lower timeframe string (e.g., '15m', '1h')
        rtf_tf: Refining timeframe string (e.g., '5m', '1m') or None
    
    Raises:
        ValueError: If rtf_tf is greater than or equal to ltf_tf
    
    Example:
        validate_timeframe_hierarchy('15m', '5m')   # OK - 5m < 15m
        validate_timeframe_hierarchy('15m', '15m')  # ERROR - equal
        validate_timeframe_hierarchy('15m', '1h')   # ERROR - 1h > 15m
    """
    if rtf_tf is None:
        return  # RTF is optional, None is valid
    
    # Timeframe to minutes mapping
    tf_to_minutes = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '2h': 120, '4h': 240, '6h': 360,
        '12h': 720, '1d': 1440,
    }
    
    # Get minutes for each timeframe
    ltf_minutes = tf_to_minutes.get(ltf_tf)
    rtf_minutes = tf_to_minutes.get(rtf_tf)
    
    # Validate that both timeframes are recognized
    if ltf_minutes is None:
        raise ValueError(
            f"Invalid LTF timeframe: '{ltf_tf}'. "
            f"Must be one of: {', '.join(sorted(tf_to_minutes.keys()))}"
        )
    
    if rtf_minutes is None:
        raise ValueError(
            f"Invalid RTF timeframe: '{rtf_tf}'. "
            f"Must be one of: {', '.join(sorted(tf_to_minutes.keys()))}"
        )
    
    # Validate that RTF < LTF
    if rtf_minutes >= ltf_minutes:
        raise ValueError(
            f"Invalid timeframe configuration: RTF ('{rtf_tf}' = {rtf_minutes}m) must be "
            f"LOWER than LTF ('{ltf_tf}' = {ltf_minutes}m). "
            f"RTF is used for entry refinement and must provide finer-grained price action. "
            f"Valid RTF options for LTF='{ltf_tf}': "
            f"{', '.join(tf for tf, mins in sorted(tf_to_minutes.items(), key=lambda x: x[1]) if mins < ltf_minutes)}"
        )


# ============================================================================
# Multi-Timeframe Timestamp Mapping
# ============================================================================

def find_htf_index_at_ltf_timestamp(
    ltf_timestamp: datetime,
    htf_candles: List[Dict[str, Any]]
) -> Optional[int]:
    """Find the most recent HTF candle index at or before LTF timestamp
    
    Uses binary search for O(log n) lookup.
    
    Args:
        ltf_timestamp: Current LTF candle timestamp (datetime object)
        htf_candles: List of HTF candles with 'timestamp' field
    
    Returns:
        Index of most recent HTF candle, or None if no valid HTF candle found
    
    Example:
        LTF: [10:00, 10:15, 10:30, 10:45, 11:00]
        HTF: [09:00, 10:00, 11:00]
        
        ltf_timestamp=10:30 -> returns htf_idx=1 (10:00 candle)
        ltf_timestamp=11:00 -> returns htf_idx=2 (11:00 candle)
    """
    if not htf_candles:
        return None
    
    # Extract timestamps for binary search
    htf_timestamps = [c['timestamp'] for c in htf_candles]
    
    # Find rightmost HTF timestamp <= ltf_timestamp
    idx = bisect.bisect_right(htf_timestamps, ltf_timestamp) - 1
    
    # Return None if no HTF candle is before or at ltf_timestamp
    if idx < 0:
        return None
    
    return idx


def find_itf_index_at_ltf_timestamp(
    ltf_timestamp: datetime,
    itf_candles: List[Dict[str, Any]]
) -> Optional[int]:
    """Find the most recent ITF candle index at or before LTF timestamp
    
    Uses binary search for O(log n) lookup.
    
    Args:
        ltf_timestamp: Current LTF candle timestamp (datetime object)
        itf_candles: List of ITF candles with 'timestamp' field
    
    Returns:
        Index of most recent ITF candle, or None if no valid ITF candle found
    
    Example:
        LTF: [10:00, 10:15, 10:30, 10:45, 11:00]
        ITF: [09:00, 10:00, 11:00]
        
        ltf_timestamp=10:30 -> returns itf_idx=1 (10:00 candle)
        ltf_timestamp=11:00 -> returns itf_idx=2 (11:00 candle)
    """
    if not itf_candles:
        return None
    
    # Extract timestamps for binary search
    itf_timestamps = [c['timestamp'] for c in itf_candles]
    
    # Find rightmost ITF timestamp <= ltf_timestamp
    idx = bisect.bisect_right(itf_timestamps, ltf_timestamp) - 1
    
    # Return None if no ITF candle is before or at ltf_timestamp
    if idx < 0:
        return None
    
    return idx


def precompute_ltf_to_htf_itf_mapping(
    ltf_candles: List[Dict[str, Any]],
    itf_candles: List[Dict[str, Any]],
    htf_candles: List[Dict[str, Any]]
) -> Tuple[List[Optional[int]], List[Optional[int]]]:
    """Precompute LTF-to-ITF and LTF-to-HTF timestamp mappings
    
    OPTIMIZATION: Instead of calling bisect on every LTF candle (O(log N) per candle),
    precompute all mappings once using a two-pointer walk (O(L + I + H) total).
    
    Args:
        ltf_candles: Lower timeframe candles (e.g., 15m)
        itf_candles: Intermediate timeframe candles (e.g., 1h)
        htf_candles: Higher timeframe candles (e.g., 4h)
    
    Returns:
        Tuple of (ltf_to_itf_idx, ltf_to_htf_idx) where:
        - ltf_to_itf_idx[i] = most recent ITF candle index at or before ltf_candles[i]
        - ltf_to_htf_idx[i] = most recent HTF candle index at or before ltf_candles[i]
        - None if no valid ITF/HTF candle found
    
    Complexity: O(len(ltf_candles) + len(itf_candles) + len(htf_candles))
    """
    ltf_to_itf_idx = []
    ltf_to_htf_idx = []
    
    # Two-pointer walk for ITF mapping
    itf_ptr = 0
    for ltf_candle in ltf_candles:
        ltf_ts = ltf_candle['timestamp']
        
        # Advance ITF pointer while next ITF candle is still <= current LTF timestamp
        while itf_ptr + 1 < len(itf_candles) and itf_candles[itf_ptr + 1]['timestamp'] <= ltf_ts:
            itf_ptr += 1
        
        # Check if current ITF candle is valid (at or before LTF timestamp)
        if itf_ptr < len(itf_candles) and itf_candles[itf_ptr]['timestamp'] <= ltf_ts:
            ltf_to_itf_idx.append(itf_ptr)
        else:
            ltf_to_itf_idx.append(None)
    
    # Two-pointer walk for HTF mapping
    htf_ptr = 0
    for ltf_candle in ltf_candles:
        ltf_ts = ltf_candle['timestamp']
        
        # Advance HTF pointer while next HTF candle is still <= current LTF timestamp
        while htf_ptr + 1 < len(htf_candles) and htf_candles[htf_ptr + 1]['timestamp'] <= ltf_ts:
            htf_ptr += 1
        
        # Check if current HTF candle is valid (at or before LTF timestamp)
        if htf_ptr < len(htf_candles) and htf_candles[htf_ptr]['timestamp'] <= ltf_ts:
            ltf_to_htf_idx.append(htf_ptr)
        else:
            ltf_to_htf_idx.append(None)
    
    return ltf_to_itf_idx, ltf_to_htf_idx


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
class OrderRecord:
    """Record of an order's complete lifecycle
    
    Tracks an order from placement through fill/expiry/cancellation
    """
    symbol: str
    side: str  # "LONG" or "SHORT"
    zone_id: str  # Unique identifier for the zone (symbol + created_at + type)
    placed_idx: int
    placed_time: Any  # timestamp
    limit_price: float  # entry price
    stop: float
    target: float
    planned_r: float
    ttl_bars: Optional[int]
    expiry_idx: Optional[int]
    status: str  # "PLACED", "FILLED", "EXPIRED", "CANCELLED"
    filled_idx: Optional[int] = None
    filled_time: Any = None
    fill_price: Optional[float] = None
    cancel_reason: Optional[str] = None


@dataclass
class DecisionFunnel:
    """Decision funnel metrics for tracking why trades were/weren't taken"""
    symbol: str
    zones_detected_ltf: int = 0  # LTF zones detected
    zones_detected_htf: int = 0  # HTF zones detected
    zones_fresh_ltf: int = 0     # LTF zones that are fresh at START of simulation
    zones_fresh_htf: int = 0     # HTF zones that are fresh at START of simulation
    zones_fresh_final: int = 0   # LTF zones that are fresh at END of simulation
    
    # NEW: Explicit CSV-based fresh counts (PR requirement A)
    zones_fresh_csv: int = 0           # Count from zones.csv where is_fresh==True (never touched)
    zones_fresh_final_csv: int = 0     # Count from zones.csv where final_is_fresh==True (fresh at end)
    zones_active_fresh_end: int = 0    # Count of active zones that are fresh at end
    
    rejected_curve: int = 0      # Rejected by curve gating
    rejected_trend: int = 0      # Rejected by trend gating
    candidates_scored: int = 0   # Candidates that passed gating and were scored
    rejected_min_setup_score: int = 0
    rejected_min_reward_risk: int = 0
    rejected_proximity: int = 0  # Rejected by proximity trigger (price too far from zone)
    refinement_attempts: int = 0  # Attempts at RTF entry refinement
    refinement_pass: int = 0      # Refinement passed (order placed)
    refinement_fail: int = 0      # Refinement failed (no order placed)
    
    # NEW: Refinement failure reasons (PR requirement C)
    refinement_fail_rejection_rule: int = 0       # Failed pattern match (engulfing/rejection/micro_break)
    refinement_fail_insufficient_candles: int = 0 # Not enough lookback candles
    refinement_fail_wrong_side: int = 0           # Price on wrong side of zone
    
    # NEW: Refinement failure debug samples (PR requirement B)
    # List of first N failures with full context (capped at 25 total per run)
    refinement_fail_samples: List[Dict[str, Any]] = None
    
    zones_attempted: int = 0      # Zones that had at least one order attempt
    zones_disabled_by_attempts: int = 0  # Zones disabled due to max attempts reached
    orders_placed: int = 0
    orders_filled: int = 0
    orders_expired_ttl: int = 0
    trades_closed: int = 0
    
    # Polarity flip metrics
    total_flips: int = 0
    flips_supply_to_demand: int = 0
    flips_demand_to_supply: int = 0
    
    # Legacy fields for backward compatibility (deprecated)
    zones_detected: int = 0
    zones_fresh: int = 0
    zones_after_curve_filter: int = 0
    zones_after_trend_filter: int = 0
    
    def __post_init__(self):
        """Initialize mutable default fields"""
        if self.refinement_fail_samples is None:
            self.refinement_fail_samples = []


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
    all_orders: List[Dict[str, Any]]  # All orders with complete lifecycle
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


def generate_synthetic_candles_mtf(
    symbol: str,
    num_ltf_candles: int,
    ltf_interval_minutes: int = 15,
    htf_interval_minutes: int = 240,  # 4h
    itf_interval_minutes: int = 60,   # 1h
    base_price: float = 100.0,
    volatility: float = 0.02,
    seed: Optional[int] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Generate synthetic candles for multiple timeframes (HTF, ITF, LTF)
    
    Creates aligned multi-timeframe candle data where higher timeframe candles
    are aggregated from lower timeframe movements.
    
    Args:
        symbol: Trading pair symbol
        num_ltf_candles: Number of LTF candles to generate
        ltf_interval_minutes: LTF candle interval in minutes (default 15m)
        htf_interval_minutes: HTF candle interval in minutes (default 240m = 4h)
        itf_interval_minutes: ITF candle interval in minutes (default 60m = 1h)
        base_price: Starting price
        volatility: Price movement volatility (0.02 = 2%)
        seed: Random seed for reproducibility
    
    Returns:
        Dict with keys 'ltf', 'itf', 'htf' containing candle lists
    """
    if seed is not None:
        random.seed(seed)
    
    # Generate LTF candles first
    ltf_candles = []
    current_price = base_price
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    for i in range(num_ltf_candles):
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
        ltf_candles.append(candle)
        
        current_price = close_price
        timestamp = timestamp + timedelta(minutes=ltf_interval_minutes)
    
    # Aggregate LTF candles into ITF candles
    itf_candles = []
    ltf_per_itf = itf_interval_minutes // ltf_interval_minutes
    for i in range(0, len(ltf_candles), ltf_per_itf):
        chunk = ltf_candles[i:i+ltf_per_itf]
        if not chunk:
            continue
        
        itf_candle = {
            'open': chunk[0]['open'],
            'high': max(c['high'] for c in chunk),
            'low': min(c['low'] for c in chunk),
            'close': chunk[-1]['close'],
            'volume': sum(c['volume'] for c in chunk),
            'timestamp': chunk[0]['timestamp'],
            'symbol': symbol,
        }
        itf_candles.append(itf_candle)
    
    # Aggregate LTF candles into HTF candles
    htf_candles = []
    ltf_per_htf = htf_interval_minutes // ltf_interval_minutes
    for i in range(0, len(ltf_candles), ltf_per_htf):
        chunk = ltf_candles[i:i+ltf_per_htf]
        if not chunk:
            continue
        
        htf_candle = {
            'open': chunk[0]['open'],
            'high': max(c['high'] for c in chunk),
            'low': min(c['low'] for c in chunk),
            'close': chunk[-1]['close'],
            'volume': sum(c['volume'] for c in chunk),
            'timestamp': chunk[0]['timestamp'],
            'symbol': symbol,
        }
        htf_candles.append(htf_candle)
    
    return {
        'ltf': ltf_candles,
        'itf': itf_candles,
        'htf': htf_candles,
    }


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


def load_candles_mtf_from_config(
    symbol: str,
    config: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Load candles for all timeframes (HTF, ITF, LTF) based on config
    
    Args:
        symbol: Trading symbol
        config: Experiment configuration with 'timeframes' section
    
    Returns:
        Dict with keys 'ltf', 'itf', 'htf' containing candle lists
    
    Raises:
        HistoricalDataError: If historical data requested but unavailable
        ValueError: If data_source is invalid or timeframes not specified
    """
    data_source = config.get('data_source', 'synthetic')
    
    # Get timeframe specifications
    timeframes = config.get('timeframes', {})
    ltf_tf = timeframes.get('ltf', '15m')
    itf_tf = timeframes.get('itf', '1h')
    htf_tf = timeframes.get('htf', '4h')
    
    # Convert timeframe strings to minutes for synthetic data
    tf_to_minutes = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '2h': 120, '4h': 240, '6h': 360,
        '12h': 720, '1d': 1440,
    }
    
    if data_source == 'synthetic':
        # Generate synthetic candles for all timeframes
        base_seed = config['data_generation']['seed']
        if base_seed is not None:
            symbol_seed = hash(symbol + str(base_seed)) % (2**31)
        else:
            symbol_seed = None
        
        ltf_minutes = tf_to_minutes.get(ltf_tf, 15)
        itf_minutes = tf_to_minutes.get(itf_tf, 60)
        htf_minutes = tf_to_minutes.get(htf_tf, 240)
        
        candles_mtf = generate_synthetic_candles_mtf(
            symbol=symbol,
            num_ltf_candles=config['data_generation']['num_candles'],
            ltf_interval_minutes=ltf_minutes,
            itf_interval_minutes=itf_minutes,
            htf_interval_minutes=htf_minutes,
            volatility=config['data_generation']['volatility'],
            seed=symbol_seed
        )
        
        return candles_mtf
    
    elif data_source == 'historical':
        # Load historical candles for each timeframe
        if 'historical_data' not in config:
            raise ValueError(
                "data_source is 'historical' but 'historical_data' section is missing in config."
            )
        
        hist_config = config['historical_data']
        exchange = hist_config.get('exchange', 'binance')
        market_type = hist_config.get('market_type', 'futures')
        data_dir = Path(hist_config.get('data_dir', './data'))
        
        # Determine date range
        use_full_history = config.get('use_full_history', False)
        
        if use_full_history:
            # Find common window across all timeframes
            required_tfs = [ltf_tf, itf_tf, htf_tf]
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
            except HistoricalDataError as e:
                raise HistoricalDataError(
                    f"Failed to determine full history window for {symbol}: {e}"
                )
        else:
            # Use explicit start/end dates from config
            start_date = config.get('start_date', '2024-01-01')
            end_date = config.get('end_date', '2024-03-31')
        
        # Load candles for each timeframe
        try:
            ltf_candles = load_historical_candles(
                symbol=symbol,
                timeframe=ltf_tf,
                start_date=start_date,
                end_date=end_date,
                data_dir=data_dir,
                exchange=exchange,
                market_type=market_type,
                return_metadata=False
            )
            
            itf_candles = load_historical_candles(
                symbol=symbol,
                timeframe=itf_tf,
                start_date=start_date,
                end_date=end_date,
                data_dir=data_dir,
                exchange=exchange,
                market_type=market_type,
                return_metadata=False
            )
            
            htf_candles = load_historical_candles(
                symbol=symbol,
                timeframe=htf_tf,
                start_date=start_date,
                end_date=end_date,
                data_dir=data_dir,
                exchange=exchange,
                market_type=market_type,
                return_metadata=False
            )
            
            return {
                'ltf': ltf_candles,
                'itf': itf_candles,
                'htf': htf_candles,
            }
        
        except HistoricalDataError as e:
            raise HistoricalDataError(
                f"Failed to load MTF historical data for {symbol}:\n{e}\n\n"
                f"Config settings:\n"
                f"  - exchange: {exchange}\n"
                f"  - market_type: {market_type}\n"
                f"  - timeframes: LTF={ltf_tf}, ITF={itf_tf}, HTF={htf_tf}\n"
                f"  - date_range: {start_date} to {end_date}\n"
                f"  - data_dir: {data_dir}\n"
            )
    
    else:
        raise ValueError(
            f"Invalid data_source: '{data_source}'. "
            f"Must be 'synthetic' or 'historical'."
        )


def execute_backtest_for_symbol(
    symbol: str,
    candles_by_tf: Dict[str, List[Dict[str, Any]]],
    params: SupplyDemandParameters,
    initial_capital: float
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], float, List[float], DecisionFunnel]:
    """Execute backtest for a single symbol using multi-timeframe analysis
    
    Args:
        symbol: Trading pair symbol
        candles_by_tf: Dict with keys 'ltf', 'itf', 'htf' containing candle lists
        params: Strategy parameters
        initial_capital: Starting capital
    
    Returns:
        Tuple of (trades, zones, orders, final_capital, equity_curve, decision_funnel)
    """
    # Optional profiling/benchmarking support
    import os
    enable_profiling = os.environ.get('SDV1_PROFILE') == '1' or os.environ.get('SDV1_BENCH') == '1'
    enable_bench = os.environ.get('SDV1_BENCH') == '1'
    
    if enable_profiling:
        import time
        stage_timings = {}
        stage_start = time.time()
    
    # Extract candles by timeframe
    ltf_candles = candles_by_tf['ltf']
    itf_candles = candles_by_tf['itf']
    htf_candles = candles_by_tf['htf']
    
    # Detect zones on all timeframes
    # LTF zones: for trade entries
    ltf_zones = detect_zones_dbr_rbd(ltf_candles, params)
    
    # HTF zones: for curve location analysis
    htf_zones = detect_zones_dbr_rbd(htf_candles, params)
    
    if enable_profiling:
        stage_timings['zone_detection'] = time.time() - stage_start
        stage_start = time.time()
    
    # OPTIMIZATION: Precompute zone freshness using vectorized operations
    from strategies.supply_demand_v1.zone_freshness_precompute import (
        precompute_zone_freshness,
        is_zone_fresh_at_idx,
        build_zone_creation_index,
        cache_zone_metrics
    )
    
    # Precompute freshness for LTF zones (used for trade entries)
    precompute_zone_freshness(ltf_zones, ltf_candles)
    zone_creation_index = build_zone_creation_index(ltf_zones)
    cache_zone_metrics(ltf_zones)
    
    # Precompute freshness for HTF zones (used for curve analysis)
    precompute_zone_freshness(htf_zones, htf_candles)
    
    if enable_profiling:
        stage_timings['freshness_precompute'] = time.time() - stage_start
        stage_start = time.time()
    
    # OPTIMIZATION: Precompute timestamp mappings once (Phase 1)
    ltf_to_itf_idx, ltf_to_htf_idx = precompute_ltf_to_htf_itf_mapping(
        ltf_candles, itf_candles, htf_candles
    )
    
    if enable_profiling:
        stage_timings['mtf_map_build'] = time.time() - stage_start
        stage_start = time.time()
    
    # OPTIMIZATION: Build HTF zone sorted structures for efficient curve lookup (Phase 3)
    # Group zones by creation index for incremental updates
    htf_supply_zones_sorted = []  # List of (proximal, zone) sorted by proximal ascending
    htf_demand_zones_sorted = []  # List of (proximal, zone) sorted by proximal descending
    
    for zone in htf_zones:
        if zone.zone_type == ZoneType.SUPPLY:
            htf_supply_zones_sorted.append((zone.proximal, zone))
        else:  # DEMAND
            htf_demand_zones_sorted.append((zone.proximal, zone))
    
    # Sort supply by proximal (ascending - lowest proximal first)
    htf_supply_zones_sorted.sort(key=lambda x: x[0])
    # Sort demand by proximal (descending - highest proximal first)
    htf_demand_zones_sorted.sort(key=lambda x: x[0], reverse=True)
    
    # Cache curve state per HTF index to avoid recomputation
    htf_curve_cache = {}  # htf_idx -> (curve_state, htf_supply_above, htf_demand_below)
    
    if enable_profiling:
        stage_timings['htf_curve_prep'] = time.time() - stage_start
        stage_start = time.time()
    
    # Initialize decision funnel tracking with MTF metrics
    funnel = DecisionFunnel(symbol=symbol)
    funnel.zones_detected_ltf = len(ltf_zones)
    funnel.zones_detected_htf = len(htf_zones)
    
    # Count fresh zones at start of simulation (index 0 for zones, but typically we start at index 100+)
    # Use the first meaningful simulation index (100) to count fresh zones
    # This represents "zones that are fresh when we start analyzing them"
    simulation_start_idx = 100  # Typical start index in the loop
    funnel.zones_fresh_ltf = sum(1 for z in ltf_zones if z.created_at <= simulation_start_idx and is_zone_fresh_at_idx(z, simulation_start_idx))
    funnel.zones_fresh_htf = sum(1 for z in htf_zones if z.created_at <= simulation_start_idx and is_zone_fresh_at_idx(z, simulation_start_idx))
    
    # Legacy fields for backward compatibility
    funnel.zones_detected = funnel.zones_detected_ltf
    funnel.zones_fresh = funnel.zones_fresh_ltf
    
    # Track capital and positions
    capital = initial_capital
    trades = []
    
    # ORDER LIFECYCLE: Single source of truth for order state
    # order_registry: Dict[order_id, order_dict] - maintains complete order lifecycle
    # Keys are unique order IDs (zone_id + placed_idx), values are order dicts with status
    order_registry: Dict[str, Dict[str, Any]] = {}
    order_id_counter = 0  # For generating unique order IDs
    
    # plan_to_order_id: Map TradePlan objects to their order_ids
    # This avoids needing to add order_id as an attribute to TradePlan dataclass
    plan_to_order_id: Dict[int, str] = {}  # Use id(plan) as key
    
    pending_plans = []  # Plans with pending orders
    open_positions = []  # Plans with filled orders (active positions)
    
    # Track equity curve for drawdown calculation
    equity_curve = [initial_capital]  # Start with initial capital
    
    # OPTIMIZATION: Build active zone manager (Phase 4)
    # Pre-bucket zones by created_at for O(1) zone activation
    # Store tuples of (zone_id, zone) for stable identification
    ltf_zones_by_creation = {}
    for zone in ltf_zones:
        zone_id = make_zone_id(symbol, zone)
        if zone.created_at not in ltf_zones_by_creation:
            ltf_zones_by_creation[zone.created_at] = []
        ltf_zones_by_creation[zone.created_at].append((zone_id, zone))
    
    # Track active zones (created but still fresh) using Dict[zone_id, zone]
    # This avoids hashability issues with mutable Zone dataclass objects
    active_zones: Dict[str, Zone] = {}
    
    # PERFORMANCE: Flip boundary index for O(log Z) polarity flip checks
    # Maintain sorted list of (distal, zone_id) for active zones
    # Only check zones where distal is between prev_close and current_close
    flip_boundary_index = []  # List of (distal, zone_id) tuples, kept sorted
    zone_id_to_distal = {}  # For efficient removal: zone_id -> distal
    
    # Track activation metrics (for debugging and validation)
    total_activations = 0
    max_active_zones = 0
    active_zones_sum = 0  # For calculating average
    active_zones_samples = 0
    
    # Track polarity flip metrics
    total_flips = 0
    flips_supply_to_demand = 0
    flips_demand_to_supply = 0
    
    # Track flip check efficiency
    flip_checks_total = 0
    flip_checks_samples = 0
    
    # ORDER DEDUPLICATION: Track active orders and order history per zone
    # active_orders_by_zone: Dict[(zone_id, side), order_info]
    # Prevents placing multiple orders for same zone at same time
    active_orders_by_zone: Dict[Tuple[str, str], Dict[str, Any]] = {}
    
    # order_history_by_zone: Dict[zone_id, List[order_attempt]]
    # Tracks all order attempts for max_retries enforcement
    order_history_by_zone: Dict[str, List[Dict[str, Any]]] = {}
    
    # zone_price_rearm_state: Dict[zone_id, Dict]
    # Tracks if zone needs price reset before re-arming
    zone_price_rearm_state: Dict[str, Dict[str, Any]] = {}
    
    # Track previous close for polarity flip detection
    prev_close = None
    
    # Simulate backtest bar by bar on LTF
    for ltf_idx in range(len(ltf_candles)):
        ltf_candle = ltf_candles[ltf_idx]
        ltf_timestamp = ltf_candle['timestamp']
        current_price = ltf_candle['close']
        current_close = current_price
        
        # OPTIMIZATION: Use precomputed O(1) mapping instead of O(log N) bisect
        htf_idx = ltf_to_htf_idx[ltf_idx]
        itf_idx = ltf_to_itf_idx[ltf_idx]
        
        # Determine curve location from HTF zones (if HTF data available)
        curve_state = CurveLocation.EQUILIBRIUM  # Default
        if htf_idx is not None and htf_idx >= 0:
            # OPTIMIZATION: Check cache first (Phase 3)
            if htf_idx in htf_curve_cache:
                curve_state, htf_supply_above, htf_demand_below = htf_curve_cache[htf_idx]
            else:
                # Find nearest fresh HTF zones using binary search on sorted lists
                htf_supply_above, htf_demand_below = None, None
                
                # Binary search for nearest supply above current price
                # Search in sorted supply zones (ascending proximal)
                for prox, zone in htf_supply_zones_sorted:
                    if zone.created_at > htf_idx:
                        continue  # Zone not created yet
                    if not is_zone_fresh_at_idx(zone, htf_idx):
                        continue  # Zone not fresh
                    if prox > current_price:
                        # First zone above price (lowest proximal > price)
                        htf_supply_above = zone
                        break
                
                # Binary search for nearest demand below current price
                # Search in sorted demand zones (descending proximal)
                for prox, zone in htf_demand_zones_sorted:
                    if zone.created_at > htf_idx:
                        continue  # Zone not created yet
                    if not is_zone_fresh_at_idx(zone, htf_idx):
                        continue  # Zone not fresh
                    if prox < current_price:
                        # First zone below price (highest proximal < price)
                        htf_demand_below = zone
                        break
                
                # Compute curve location
                curve_state = curve_location(current_price, htf_supply_above, htf_demand_below)
                
                # Cache result for this HTF index
                htf_curve_cache[htf_idx] = (curve_state, htf_supply_above, htf_demand_below)
        
        # Determine trend direction from ITF candles (if ITF data available)
        trend_state = TrendDirection.SIDEWAYS  # Default
        if itf_idx is not None and itf_idx >= 100:  # Need sufficient history
            # OPTIMIZATION: Use new API that doesn't slice (Phase 2)
            trend_state = trend_direction_itf(itf_candles, itf_idx, params)
        
        # Check for fills on pending orders (LTF fills only)
        for plan in list(pending_plans):
            # WORKAROUND: Enum comparison failing (likely duplicate imports), compare values instead
            if str(plan.order_state.value if hasattr(plan.order_state, 'value') else plan.order_state) == 'pending':
                try:
                    # Get order_id from mapping (not from plan attribute)
                    plan_id = id(plan)
                    order_id = plan_to_order_id.get(plan_id)
                except Exception as e:
                    print(f"⚠️  EXCEPTION in pending check: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                
                if order_id is None:
                    # This should not happen - it means plan was not registered
                    print(f"⚠️  WARNING: Plan without order_id mapping at idx {ltf_idx}, placed_at {plan.placed_at_idx}")
                    print(f"   This indicates a bug in order placement logic.")
                    # Skip this plan
                    pending_plans.remove(plan)
                    continue
                
                # Check TTL expiration first
                if params.ttl_bars and (ltf_idx - plan.placed_at_idx) >= params.ttl_bars:
                    plan.order_state = OrderState.CANCELLED
                    pending_plans.remove(plan)
                    
                    # ORDER DEDUPLICATION: Remove from active_orders_by_zone and set price reset flag
                    plan_zone_id = make_zone_id(symbol, plan.zone)
                    expiry_polarity = get_zone_polarity_at_idx(plan.zone, plan.placed_at_idx)
                    side_expiry = 'LONG' if expiry_polarity == ZoneType.DEMAND else 'SHORT'
                    order_key_expiry = (plan_zone_id, side_expiry)
                    if order_key_expiry in active_orders_by_zone:
                        del active_orders_by_zone[order_key_expiry]
                    
                    # Set price reset requirement if configured
                    if params.rearm_requires_price_reset:
                        zone_price_rearm_state[plan_zone_id] = {
                            'needs_reset': True,
                            'last_expiry_idx': ltf_idx,
                        }
                    
                    # Update order record in registry with expiry
                    if order_id in order_registry:
                        order_registry[order_id]['status'] = 'EXPIRED'
                        order_registry[order_id]['cancel_reason'] = 'TTL_EXPIRED'
                        order_registry[order_id]['expiry_idx'] = ltf_idx
                    
                    continue
                
                # Check for fill
                filled = check_limit_order_fill(
                    plan,
                    ltf_candles,
                    ltf_idx,
                    params
                )
                if filled:
                    plan.order_state = OrderState.FILLED
                    plan.filled_at_idx = ltf_idx
                    
                    # ORDER DEDUPLICATION: Remove from active_orders_by_zone (order is filled)
                    plan_zone_id = make_zone_id(symbol, plan.zone)
                    entry_polarity_fill = get_zone_polarity_at_idx(plan.zone, ltf_idx)
                    side_fill = 'LONG' if entry_polarity_fill == ZoneType.DEMAND else 'SHORT'
                    order_key_fill = (plan_zone_id, side_fill)
                    if order_key_fill in active_orders_by_zone:
                        del active_orders_by_zone[order_key_fill]
                    
                    # Update order record in registry with fill
                    if order_id in order_registry:
                        order_registry[order_id]['status'] = 'FILLED'
                        order_registry[order_id]['filled_idx'] = ltf_idx
                        order_registry[order_id]['filled_time'] = ltf_candle.get('timestamp')
                        order_registry[order_id]['fill_price'] = plan.actual_entry_price or plan.entry_price
                    
                    # Move from pending to open positions
                    pending_plans.remove(plan)
                    open_positions.append(plan)
                    
                    # Create trade record (entry) with curve and trend state
                    # Use polarity at entry time for trade side determination
                    entry_polarity = get_zone_polarity_at_idx(plan.zone, ltf_idx)
                    trades.append({
                        'symbol': symbol,
                        'side': 'LONG' if entry_polarity == ZoneType.DEMAND else 'SHORT',
                        'entry': plan.actual_entry_price or plan.entry_price,
                        'stop': plan.stop_loss,
                        'target': plan.take_profit,
                        'planned_R': plan.r_multiple,
                        'planned_r': plan.r_multiple,  # Add lowercase for integrity validation
                        'realized_R': None,  # Will be filled on exit
                        'entry_time': ltf_candle.get('timestamp'),
                        'entry_idx': ltf_idx,
                        'exit_time': None,
                        'exit_idx': None,
                        'exit_reason': None,
                        'score': plan.score,
                        'curve_state': enum_to_string(curve_state),  # Now properly tracked
                        'trend_state': enum_to_string(trend_state),  # Now properly tracked
                        'zone_created_at': plan.zone.created_at,
                        'pnl': 0.0,
                        'position_size': plan.position_size,
                        # Polarity tracking
                        'polarity_type_at_entry': enum_to_string(entry_polarity),
                        'flip_count_at_entry': plan.zone.flip_count,
                    })
        
        # Check for exits on open positions
        for plan in list(open_positions):
            # Use polarity at entry (stored in plan) for position direction
            # Get polarity from the corresponding trade record
            plan_entry_idx = plan.filled_at_idx
            entry_polarity = get_zone_polarity_at_idx(plan.zone, plan_entry_idx) if plan_entry_idx is not None else plan.zone.zone_type
            is_long = entry_polarity == ZoneType.DEMAND
            
            # Check for intrabar stop or target hit
            exit_reason = check_intrabar_exit(
                plan,
                ltf_candle,
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
                    exit_price = ltf_candle['close']
                
                # Calculate P&L (includes all costs)
                pnl = calculate_pnl_with_costs(
                    plan,
                    exit_price,
                    params
                )
                
                # Calculate realized_R based on exit reason
                # Use actual_entry_price (which includes entry costs) for R calculation
                entry = plan.actual_entry_price or plan.entry_price
                stop = plan.stop_loss
                risk = abs(entry - stop)
                
                if exit_reason == "STOP":
                    # Stop loss hit: realized_R should be approximately -1.0
                    # Account for exit costs in the R calculation
                    exit_cost_pct = (params.fees_bps + params.slippage_bps) / 10000.0
                    if is_long:
                        # Exit at stop - exit_costs
                        actual_exit = stop * (1 - exit_cost_pct)
                        realized_r = (actual_exit - entry) / risk if risk > 0 else -1.0
                    else:
                        # Exit at stop + exit_costs
                        actual_exit = stop * (1 + exit_cost_pct)
                        realized_r = (entry - actual_exit) / risk if risk > 0 else -1.0
                elif exit_reason == "TARGET":
                    # Target hit: realized_R should be approximately +planned_R
                    # Account for exit costs
                    exit_cost_pct = (params.fees_bps + params.slippage_bps) / 10000.0
                    if is_long:
                        # Exit at target - exit_costs
                        actual_exit = exit_price * (1 - exit_cost_pct)
                        realized_r = (actual_exit - entry) / risk if risk > 0 else plan.r_multiple
                    else:
                        # Exit at target + exit_costs
                        actual_exit = exit_price * (1 + exit_cost_pct)
                        realized_r = (entry - actual_exit) / risk if risk > 0 else plan.r_multiple
                else:
                    # EOD close or other: calculate actual R based on exit price
                    exit_cost_pct = (params.fees_bps + params.slippage_bps) / 10000.0
                    if is_long:
                        actual_exit = exit_price * (1 - exit_cost_pct)
                        realized_r = (actual_exit - entry) / risk if risk > 0 else 0
                    else:
                        actual_exit = exit_price * (1 + exit_cost_pct)
                        realized_r = (entry - actual_exit) / risk if risk > 0 else 0
                
                # Update trade record
                for trade in trades:
                    if (trade['entry_idx'] == plan.filled_at_idx and 
                        trade['symbol'] == symbol and
                        trade['exit_idx'] is None):
                        trade['realized_R'] = realized_r
                        trade['exit_time'] = ltf_candle.get('timestamp')
                        trade['exit_idx'] = ltf_idx
                        trade['exit_reason'] = exit_reason
                        trade['pnl'] = pnl
                        break
                
                # Update capital
                capital += pnl
                equity_curve.append(capital)
                
                # Remove from open positions
                open_positions.remove(plan)
                funnel.trades_closed += 1
            else:
                # No exit, manage trade (update stops if needed)
                management = manage_trade_plan(
                    plan,
                    ltf_candle['close'],
                    params
                )
                
                # Update stop if breakeven move triggered
                if management.get("update_stop") is not None:
                    plan.stop_loss = management["update_stop"]
        
        # OPTIMIZATION: Update active zones at this index (Phase 4)
        # Add newly created zones
        if ltf_idx in ltf_zones_by_creation:
            for zone_id, zone in ltf_zones_by_creation[ltf_idx]:
                active_zones[zone_id] = zone
                total_activations += 1
                
                # PERFORMANCE: Add to flip boundary index
                distal = zone.distal
                bisect.insort(flip_boundary_index, (distal, zone_id))
                zone_id_to_distal[zone_id] = distal
        
        # Remove zones that just became non-fresh
        # IMPORTANT: Collect zone_ids first, then delete after iteration
        zone_ids_to_remove = []
        for zone_id, zone in active_zones.items():
            if not is_zone_fresh_at_idx(zone, ltf_idx):
                zone_ids_to_remove.append(zone_id)
        
        for zone_id in zone_ids_to_remove:
            del active_zones[zone_id]
            
            # PERFORMANCE: Remove from flip boundary index
            if zone_id in zone_id_to_distal:
                distal = zone_id_to_distal[zone_id]
                try:
                    flip_boundary_index.remove((distal, zone_id))
                except ValueError:
                    pass  # Already removed or not present
                del zone_id_to_distal[zone_id]
        
        # Update tracking metrics
        active_zones_sum += len(active_zones)
        active_zones_samples += 1
        if len(active_zones) > max_active_zones:
            max_active_zones = len(active_zones)
        
        # PERFORMANCE: Update polarity for zones whose flip boundary was crossed
        # Only check zones where distal is between prev_close and current_close
        if prev_close is not None and ltf_idx > 0 and len(flip_boundary_index) > 0:
            lo = min(prev_close, current_close)
            hi = max(prev_close, current_close)
            
            # Use bisect to find zones with distal in (lo, hi]
            # Find leftmost index where distal > lo
            left_idx = bisect.bisect_left(flip_boundary_index, (lo, ''))
            # Find rightmost index where distal <= hi
            right_idx = bisect.bisect_right(flip_boundary_index, (hi, '\uffff'))
            
            # Only check candidate zones (those whose distal was crossed)
            candidate_zones = flip_boundary_index[left_idx:right_idx]
            flip_checks_total += len(candidate_zones)
            flip_checks_samples += 1
            
            for distal, zone_id in candidate_zones:
                # Verify zone is still active (lazy deletion guard)
                if zone_id not in active_zones:
                    continue
                
                zone = active_zones[zone_id]
                polarity_before = get_zone_polarity_at_idx(zone, ltf_idx - 1)
                flipped = check_polarity_flip(zone, ltf_idx, current_close, prev_close)
                
                if flipped:
                    polarity_after = zone.polarity_type
                    total_flips += 1
                    if polarity_before == ZoneType.SUPPLY and polarity_after == ZoneType.DEMAND:
                        flips_supply_to_demand += 1
                    elif polarity_before == ZoneType.DEMAND and polarity_after == ZoneType.SUPPLY:
                        flips_demand_to_supply += 1
        
        # Store prev_close for next iteration
        prev_close = current_close
        
        # Look for new setups - only check ACTIVE zones (Phase 4 + Phase 5)
        if ltf_idx > 100:  # Need some history for analysis
            for zone_id, zone in active_zones.items():
                # Zone is guaranteed to be created and fresh (by active_zones dict)
                
                # CHECK IF ZONE IS DISABLED: Skip zones that exceeded max attempts
                if zone.disabled:
                    continue  # Zone disabled, skip entirely (no refinement, no scoring)
                
                # CHECK COOLDOWN: If cooldown is enabled, allow retry after cooldown period
                if zone.attempts >= params.max_attempts_per_zone:
                    if params.cooldown_bars is not None and zone.last_attempt_idx is not None:
                        # Check if cooldown period has elapsed
                        bars_since_attempt = ltf_idx - zone.last_attempt_idx
                        if bars_since_attempt >= params.cooldown_bars:
                            # Cooldown period elapsed, re-enable zone (reset attempts)
                            zone.attempts = 0
                            zone.last_attempt_idx = None
                            zone.disabled = False
                        else:
                            # Still in cooldown, skip
                            continue
                    else:
                        # No cooldown configured, disable zone permanently
                        if not zone.disabled:
                            zone.disabled = True
                            funnel.zones_disabled_by_attempts += 1
                        continue
                
                # PROXIMITY TRIGGER: Skip zones that were just created
                # Zones need time to "cool off" before we consider placing orders
                # This prevents placing orders at zone creation (not a retest)
                zone_age = ltf_idx - zone.created_at
                min_zone_age = 5  # Minimum bars before zone is eligible for order placement
                if zone_age < min_zone_age:
                    continue  # Zone too young, skip
                
                # Check if we already have a pending order or position for this zone
                zone_already_traded = any(
                    p.zone == zone for p in pending_plans + open_positions
                )
                if zone_already_traded:
                    continue
                
                # ORDER DEDUPLICATION: Check if zone already has an active order
                # Determine side based on current polarity
                zone_polarity_check = get_zone_polarity_at_idx(zone, ltf_idx)
                side_str = 'LONG' if zone_polarity_check == ZoneType.DEMAND else 'SHORT'
                order_key = (zone_id, side_str)
                
                # Check if there's already an active order for this zone
                if order_key in active_orders_by_zone:
                    continue  # Skip - already have active order for this zone
                
                # Check order history for max_retries enforcement
                if zone_id in order_history_by_zone:
                    attempts = len(order_history_by_zone[zone_id])
                    if attempts >= params.max_retries_per_zone:
                        continue  # Max retries reached for this zone
                
                # Check if price reset is required for re-arming
                if params.rearm_requires_price_reset and zone_id in zone_price_rearm_state:
                    rearm_info = zone_price_rearm_state[zone_id]
                    needs_reset = rearm_info.get('needs_reset', False)
                    
                    if needs_reset:
                        # Check if price has moved away from zone (beyond proximal + buffer)
                        proximal = zone.proximal
                        buffer = abs(proximal) * params.rearm_price_buffer_pct
                        
                        if zone_polarity_check == ZoneType.DEMAND:
                            # For demand, price must go above proximal + buffer
                            price_reset = current_price > (proximal + buffer)
                        else:
                            # For supply, price must go below proximal - buffer
                            price_reset = current_price < (proximal - buffer)
                        
                        if not price_reset:
                            continue  # Price hasn't reset, can't place new order
                        else:
                            # Price has reset, clear the needs_reset flag
                            zone_price_rearm_state[zone_id]['needs_reset'] = False
                
                # === REORDERED PIPELINE (PR requirement B) ===
                # New order: curve/trend gating → proximity → scoring → refinement → order
                # This avoids expensive scoring for zones that fail cheap proximity checks
                
                # STEP 1: Apply MTF gating (cheap per-zone check)
                # Convert curve and trend to string format for should_allow_trade
                curve_str = enum_to_string(curve_state)
                trend_str = enum_to_string(trend_state)
                
                # Placeholder score for gating check (we'll compute actual score after proximity+gating)
                base_score = 0.0
                
                # Check if trade should be allowed based on curve + trend gating
                allowed, adjusted_score = should_allow_trade(
                    zone,
                    curve_str,
                    trend_str,
                    base_score,
                    params
                )
                
                if not allowed:
                    # Track rejection reason (simplified logic)
                    if curve_str in ["high", "low"]:
                        # Rejected due to curve position (HIGH blocks DEMAND, LOW blocks SUPPLY)
                        funnel.rejected_curve += 1
                    else:
                        # Rejected due to trend misalignment or sideways (for EQ zones)
                        funnel.rejected_trend += 1
                    continue
                
                # STEP 2: PROXIMITY TRIGGER (cheap per-candle check) - MOVED BEFORE SCORING
                # Only evaluate zones when price is near them
                # This prevents expensive scoring for distant zones
                zone_polarity_now = get_zone_polarity_at_idx(zone, ltf_idx)
                
                # Calculate zone width
                zone_width = abs(zone.distal - zone.proximal)
                
                # Determine entry price (limit price where order will be placed)
                # For DEMAND (LONG): entry at proximal (buy when price drops to zone)
                # For SUPPLY (SHORT): entry at proximal (sell when price rises to zone)
                limit_price = zone.proximal
                
                # Calculate distance from current price to limit price
                distance_to_entry = abs(current_price - limit_price)
                
                # Calculate proximity threshold
                proximity_threshold = max(
                    params.entry_proximity_abs,
                    params.entry_proximity_zone_width_mult * zone_width
                )
                
                # Check if price is within proximity threshold
                if distance_to_entry > proximity_threshold:
                    funnel.rejected_proximity += 1
                    continue
                
                # Optional: Check if price is on correct side and approaching
                if params.require_price_on_correct_side:
                    if zone_polarity_now == ZoneType.DEMAND:
                        # For DEMAND (LONG), price should be above zone (can drop into it)
                        # We want to place when price is near but hasn't fully entered yet
                        if current_price < zone.distal:
                            # Price is below the zone entirely, skip
                            funnel.rejected_proximity += 1
                            continue
                    else:  # SUPPLY
                        # For SUPPLY (SHORT), price should be below zone (can rise into it)
                        # We want to place when price is near but hasn't fully entered yet
                        if current_price > zone.distal:
                            # Price is above the zone entirely, skip
                            funnel.rejected_proximity += 1
                            continue
                
                # STEP 3: SCORING (expensive - only if proximity passes)
                # Find opposing zone (nearest fresh zone of opposite type)
                # Use dynamic polarity for zone type determination
                opposing_zone = None
                if zone_polarity_now == ZoneType.DEMAND:
                    # Find nearest fresh supply above
                    for z in ltf_zones:
                        z_polarity = get_zone_polarity_at_idx(z, ltf_idx)
                        if z_polarity == ZoneType.SUPPLY and z.proximal > current_price:
                            if z.created_at < ltf_idx and is_zone_fresh_at_idx(z, ltf_idx):
                                if opposing_zone is None or z.proximal < opposing_zone.proximal:
                                    opposing_zone = z
                else:  # SUPPLY
                    # Find nearest fresh demand below
                    for z in ltf_zones:
                        z_polarity = get_zone_polarity_at_idx(z, ltf_idx)
                        if z_polarity == ZoneType.DEMAND and z.proximal < current_price:
                            if z.created_at < ltf_idx and is_zone_fresh_at_idx(z, ltf_idx):
                                if opposing_zone is None or z.proximal > opposing_zone.proximal:
                                    opposing_zone = z
                
                score = odds_enhancer_score(
                    zone,
                    current_price,
                    curve_state,
                    trend_state,
                    params,
                    opposing_zone
                )
                funnel.candidates_scored += 1
                
                if score < params.min_setup_score:
                    funnel.rejected_min_setup_score += 1
                    continue
                
                # STEP 4: RTF ENTRY REFINEMENT (only if score passes)
                # Check if refinement criteria are met
                # If refinement fails, skip order but keep zone active for future attempts
                funnel.refinement_attempts += 1
                
                # Updated to handle 3-tuple return: (passed, failure_reason, debug_info)
                refinement_passed, failure_reason, debug_info = check_rtf_refinement(
                    ltf_candles,
                    ltf_idx,
                    zone,
                    zone_polarity_now,
                    params
                )
                
                if not refinement_passed:
                    # Refinement failed - track reason and skip order placement
                    funnel.refinement_fail += 1
                    
                    # Track specific failure reason (PR requirement C)
                    if failure_reason == "insufficient_candles":
                        funnel.refinement_fail_insufficient_candles += 1
                    elif failure_reason == "rejection_rule":
                        funnel.refinement_fail_rejection_rule += 1
                    elif failure_reason == "wrong_side":
                        funnel.refinement_fail_wrong_side += 1
                    
                    # === PR REQUIREMENT B: Debug sampling for refinement failures ===
                    # Sample first N failures (cap at 25 per run) with full context
                    MAX_SAMPLES = 25
                    if len(funnel.refinement_fail_samples) < MAX_SAMPLES:
                        # Build compact sample with all relevant context
                        sample = {
                            "symbol": symbol,
                            "idx": ltf_idx,
                            "side": "LONG" if zone_polarity_now == ZoneType.DEMAND else "SHORT",
                            "zone_id": make_zone_id(symbol, zone),
                            "failure_reason": failure_reason,
                        }
                        
                        # Add candle OHLC if available
                        if ltf_idx < len(ltf_candles):
                            candle = ltf_candles[ltf_idx]
                            sample["candle"] = {
                                "open": candle.get("open"),
                                "high": candle.get("high"),
                                "low": candle.get("low"),
                                "close": candle.get("close"),
                            }
                        
                        # Add debug_info (computed metrics and specific failure details)
                        if debug_info:
                            # Extract relevant fields for compactness
                            # Avoid duplicating large candle dict
                            sample["computed_metrics"] = {
                                k: v for k, v in debug_info.items()
                                if k not in ["candle", "previous_candle", "zone_id"]
                            }
                        
                        funnel.refinement_fail_samples.append(sample)
                    
                    continue
                
                # Refinement passed (or disabled) - proceed with order placement
                funnel.refinement_pass += 1
                
                # Build trade plan
                plan = build_trade_plan(
                    zone,
                    current_price,
                    capital,
                    params,
                    opposing_zone,
                    score
                )
                
                if not plan or plan.r_multiple < params.min_reward_risk:
                    funnel.rejected_min_reward_risk += 1
                    continue
                
                # Place order
                plan.placed_at_idx = ltf_idx
                
                # INCREMENT ZONE ATTEMPTS: Track that this zone has an order placed
                # This happens ONLY when order enters PLACED state, not on refinement attempt
                if zone.attempts == 0:
                    funnel.zones_attempted += 1  # First attempt on this zone
                zone.attempts += 1
                zone.last_attempt_idx = ltf_idx
                
                # Generate unique order ID
                order_id = f"{symbol}_{order_id_counter}"
                order_id_counter += 1
                
                # Map plan to order_id (can't add as attribute to dataclass)
                plan_id = id(plan)
                plan_to_order_id[plan_id] = order_id
                
                # === SAME-CANDLE FILL CHECK (PR REQUIREMENT B) ===
                # Check if the order can fill immediately on the same candle where it's placed
                # This allows for same-candle fills when price has already touched the limit
                same_candle_filled = check_limit_order_fill(
                    plan,
                    ltf_candles,
                    ltf_idx,
                    params
                )
                
                if same_candle_filled:
                    # Order filled on same candle - skip adding to pending_plans
                    # Update order record in registry with fill
                    order_registry_entry = {
                        'symbol': symbol,
                        'side': 'LONG' if get_zone_polarity_at_idx(zone, ltf_idx) == ZoneType.DEMAND else 'SHORT',
                        'zone_id': make_zone_id(symbol, zone),
                        'placed_idx': ltf_idx,
                        'placed_time': ltf_candle.get('timestamp'),
                        'limit_price': plan.entry_price,
                        'stop': plan.stop_loss,
                        'target': plan.take_profit,
                        'planned_r': plan.r_multiple,
                        'ttl_bars': params.ttl_bars,
                        'expiry_idx': ltf_idx + params.ttl_bars if params.ttl_bars else None,
                        'status': 'FILLED',
                        'filled_idx': ltf_idx,
                        'filled_time': ltf_candle.get('timestamp'),
                        'fill_price': plan.actual_entry_price or plan.entry_price,
                        'cancel_reason': None,
                        'curve_state': enum_to_string(curve_state),
                        'trend_state': enum_to_string(trend_state),
                        'polarity_type_at_order': enum_to_string(get_zone_polarity_at_idx(zone, ltf_idx)),
                        'flip_count_at_order': zone.flip_count,
                    }
                    order_registry[order_id] = order_registry_entry
                    
                    # Move directly to open positions (skip pending_plans)
                    open_positions.append(plan)
                    
                    # Create trade record (entry)
                    entry_polarity = get_zone_polarity_at_idx(plan.zone, ltf_idx)
                    trades.append({
                        'symbol': symbol,
                        'side': 'LONG' if entry_polarity == ZoneType.DEMAND else 'SHORT',
                        'entry': plan.actual_entry_price or plan.entry_price,
                        'stop': plan.stop_loss,
                        'target': plan.take_profit,
                        'planned_R': plan.r_multiple,
                        'planned_r': plan.r_multiple,
                        'realized_R': None,  # Will be set on exit
                        'entry_time': ltf_candle.get('timestamp'),
                        'entry_idx': ltf_idx,
                        'exit_time': None,
                        'exit_idx': None,
                        'exit_reason': None,
                        'score': score,
                        'curve_state': enum_to_string(curve_state),
                        'trend_state': enum_to_string(trend_state),
                        'zone_created_at': zone.created_at,
                        'pnl': None,
                        'position_size': plan.position_size,
                        'polarity_type_at_entry': enum_to_string(entry_polarity),
                        'flip_count_at_entry': zone.flip_count,
                    })
                    funnel.orders_filled += 1
                    
                    # ORDER DEDUPLICATION: Do NOT register in active_orders_by_zone
                    # since order is already filled
                    
                    continue  # Skip the rest of order placement logic
                
                # Order not filled on same candle - add to pending_plans
                pending_plans.append(plan)
                
                # Create order record with curve and trend state
                # Use dynamic polarity at order placement time
                order_polarity = get_zone_polarity_at_idx(zone, ltf_idx)
                # Use make_zone_id for consistency
                side = 'LONG' if order_polarity == ZoneType.DEMAND else 'SHORT'
                expiry_idx = ltf_idx + params.ttl_bars if params.ttl_bars else None
                
                # ORDER DEDUPLICATION: Register this order in active_orders_by_zone
                order_key = (zone_id, side)
                order_info = {
                    'zone_id': zone_id,
                    'side': side,
                    'placed_idx': ltf_idx,
                    'expiry_idx': expiry_idx,
                    'plan': plan,
                    'order_id': order_id,
                }
                active_orders_by_zone[order_key] = order_info
                
                # Track order history for this zone
                if zone_id not in order_history_by_zone:
                    order_history_by_zone[zone_id] = []
                order_history_by_zone[zone_id].append({
                    'placed_idx': ltf_idx,
                    'side': side,
                    'expiry_idx': expiry_idx,
                })
                
                # Add order to registry (single source of truth)
                order_registry[order_id] = {
                    'symbol': symbol,
                    'side': side,
                    'zone_id': zone_id,
                    'placed_idx': ltf_idx,
                    'placed_time': ltf_candle.get('timestamp'),
                    'limit_price': plan.entry_price,
                    'stop': plan.stop_loss,
                    'target': plan.take_profit,
                    'planned_r': plan.r_multiple,
                    'ttl_bars': params.ttl_bars,
                    'expiry_idx': expiry_idx,
                    'status': 'PLACED',
                    'filled_idx': None,
                    'filled_time': None,
                    'fill_price': None,
                    'cancel_reason': None,
                    'curve_state': enum_to_string(curve_state),
                    'trend_state': enum_to_string(trend_state),
                    # Polarity tracking
                    'polarity_type_at_order': enum_to_string(order_polarity),
                    'flip_count_at_order': zone.flip_count,
                }
    
    # Close any remaining open positions at EOD (end of data)
    if ltf_candles:
        for plan in open_positions:
            # Use polarity at entry for EOD close
            plan_entry_idx = plan.filled_at_idx
            entry_polarity = get_zone_polarity_at_idx(plan.zone, plan_entry_idx) if plan_entry_idx is not None else plan.zone.zone_type
            is_long = entry_polarity == ZoneType.DEMAND
            exit_price = ltf_candles[-1]['close']
            
            pnl = calculate_pnl_with_costs(plan, exit_price, params)
            
            # Calculate realized_R with exit costs for EOD close
            entry = plan.actual_entry_price or plan.entry_price
            stop = plan.stop_loss
            risk = abs(entry - stop)
            
            exit_cost_pct = (params.fees_bps + params.slippage_bps) / 10000.0
            if is_long:
                actual_exit = exit_price * (1 - exit_cost_pct)
                realized_r = (actual_exit - entry) / risk if risk > 0 else 0
            else:
                actual_exit = exit_price * (1 + exit_cost_pct)
                realized_r = (entry - actual_exit) / risk if risk > 0 else 0
            
            # Update trade record
            for trade in trades:
                if (trade['entry_idx'] == plan.filled_at_idx and 
                    trade['symbol'] == symbol and
                    trade['exit_idx'] is None):
                    trade['realized_R'] = realized_r
                    trade['exit_time'] = ltf_candles[-1].get('timestamp')
                    trade['exit_idx'] = len(ltf_candles) - 1
                    trade['exit_reason'] = 'EOD_CLOSE'
                    trade['pnl'] = pnl
                    break
            
            capital += pnl
            equity_curve.append(capital)
            funnel.trades_closed += 1
    
    # Calculate zones_fresh_final: count zones that are fresh at END of simulation
    end_idx = len(ltf_candles) - 1
    funnel.zones_fresh_final = sum(1 for z in ltf_zones if is_zone_fresh_at_idx(z, end_idx))
    
    # === PR REQUIREMENT A: Calculate CSV-based fresh counts ===
    # These will be compared against zones.csv to validate correctness
    # Count from zone_dicts (which will be written to zones.csv)
    # We'll compute them here first, then use them again when building zone_dicts
    
    # Count zones where is_fresh==True (never touched during entire simulation)
    # is_fresh is inverted from ever_touched: is_fresh = not ever_touched
    zones_never_touched = [z for z in ltf_zones if not z.ever_touched]
    funnel.zones_fresh_csv = len(zones_never_touched)
    
    # Count zones that are fresh at END (final_is_fresh==True)
    zones_fresh_at_end = [z for z in ltf_zones if is_zone_fresh_at_idx(z, end_idx)]
    funnel.zones_fresh_final_csv = len(zones_fresh_at_end)
    
    # Track active zones that are still fresh at end (for observability)
    # Active = created and not disabled
    active_zones_at_end = [z for z in ltf_zones if z.created_at <= end_idx and not z.disabled]
    funnel.zones_active_fresh_end = sum(1 for z in active_zones_at_end if is_zone_fresh_at_idx(z, end_idx))
    
    # DECISION FUNNEL: Recompute counts from final order_registry state
    # This ensures funnel matches orders.csv and prevents mismatches
    orders_list = list(order_registry.values())
    funnel.orders_placed = len(orders_list)
    funnel.orders_filled = sum(1 for o in orders_list if o['status'] == 'FILLED')
    funnel.orders_expired_ttl = sum(1 for o in orders_list if o['status'] == 'EXPIRED')
    
    # Calculate and print runtime sanity metrics
    avg_active_zones = active_zones_sum / active_zones_samples if active_zones_samples > 0 else 0.0
    avg_flip_checks = flip_checks_total / flip_checks_samples if flip_checks_samples > 0 else 0.0
    
    # Print activation metrics (useful for debugging)
    print(f"\n{'='*80}")
    print(f"ACTIVE ZONE MANAGER METRICS - {symbol}")
    print(f"{'='*80}")
    print(f"{'Total Activations':30s}: {total_activations}")
    print(f"{'Max Active Zones':30s}: {max_active_zones}")
    print(f"{'Avg Active Zones':30s}: {avg_active_zones:.2f}")
    print(f"{'Zones Detected (LTF)':30s}: {len(ltf_zones)}")
    print(f"{'Candidates Scored':30s}: {funnel.candidates_scored}")
    print(f"{'Orders Placed':30s}: {funnel.orders_placed}")
    print(f"")
    print(f"{'='*80}")
    print(f"ORDER STATUS SUMMARY - {symbol}")
    print(f"{'='*80}")
    print(f"{'Orders Placed':30s}: {funnel.orders_placed}")
    print(f"{'Orders Filled':30s}: {funnel.orders_filled}")
    print(f"{'Orders Expired (TTL)':30s}: {funnel.orders_expired_ttl}")
    print(f"{'Orders Still Pending':30s}: {funnel.orders_placed - funnel.orders_filled - funnel.orders_expired_ttl}")
    print(f"")
    print(f"{'='*80}")
    print(f"POLARITY FLIP PERFORMANCE - {symbol}")
    print(f"{'='*80}")
    print(f"{'Total Flips':30s}: {total_flips}")
    print(f"{'Avg Flip Checks/Candle':30s}: {avg_flip_checks:.2f}")
    print(f"{'Flip Check Efficiency':30s}: {(avg_flip_checks / avg_active_zones * 100 if avg_active_zones > 0 else 0):.1f}% of active zones")
    print(f"{'Expected if no index':30s}: {avg_active_zones:.2f} checks/candle")
    
    # Sanity check: If zones detected but no activations, something is wrong
    if len(ltf_zones) > 0 and total_activations == 0:
        print(f"\n⚠️  WARNING: {len(ltf_zones)} zones detected but ZERO activations!")
        print(f"   This indicates ltf_zones_by_creation is not being populated correctly.")
        print(f"   Check that zone.created_at values are within [0, {len(ltf_candles)-1}]")
        
        # Debug info: Show created_at range
        created_at_values = [z.created_at for z in ltf_zones]
        if created_at_values:
            print(f"   Zone created_at range: [{min(created_at_values)}, {max(created_at_values)}]")
            print(f"   LTF candle index range: [0, {len(ltf_candles)-1}]")
    
    print(f"{'='*80}\n")
    
    if enable_profiling:
        stage_timings['backtest_loop'] = time.time() - stage_start
        stage_start = time.time()
    
    # Convert zones to dicts for output (LTF zones only, as these are the entry zones)
    # Calculate final freshness at end of simulation
    end_idx = len(ltf_candles) - 1
    zone_dicts = []
    for zone in ltf_zones:
        # Calculate final_is_fresh: is zone fresh at the END of the simulation?
        final_is_fresh = is_zone_fresh_at_idx(zone, end_idx)
        
        # Get final polarity at end of simulation
        final_polarity = get_zone_polarity_at_idx(zone, end_idx)
        
        zone_dicts.append({
            'symbol': symbol,
            'zone_type': zone.zone_type.value,  # Original detection type
            'proximal': zone.proximal,
            'distal': zone.distal,
            'created_at': zone.created_at,
            'base_len': zone.base_len,
            'legout_len': zone.legout_len,
            'legout_return': zone.legout_return,
            'freshness_touches': zone.freshness_touches,
            'first_touch_idx': zone.first_touch_idx,  # When first touched (None if never)
            'ever_touched': zone.ever_touched,  # Was it EVER touched?
            'final_is_fresh': final_is_fresh,  # Is it fresh at END of simulation?
            # DEPRECATED: kept for backward compatibility
            'is_fresh': zone.is_fresh,  # Same as ever_touched (inverted)
            # Polarity fields
            'original_type': zone.original_type.value if zone.original_type else zone.zone_type.value,
            'final_polarity_type': final_polarity.value,
            'flip_count': zone.flip_count,
            'last_flip_idx': zone.last_flip_idx,
            # Attempt tracking fields
            'attempts': zone.attempts,
            'last_attempt_idx': zone.last_attempt_idx,
            'disabled': zone.disabled,
        })
    
    if enable_profiling:
        stage_timings['output_conversion'] = time.time() - stage_start
        
        # Print profiling results
        print("\n" + "=" * 80)
        if enable_bench:
            print(f"BENCHMARK RESULTS - {symbol}")
        else:
            print(f"PROFILING RESULTS - {symbol}")
        print("=" * 80)
        total_time = sum(stage_timings.values())
        for stage, timing in stage_timings.items():
            pct = (timing / total_time * 100) if total_time > 0 else 0
            print(f"{stage:25s}: {timing:7.3f}s ({pct:5.1f}%)")
        print(f"{'TOTAL':25s}: {total_time:7.3f}s")
        
        # Additional benchmarking stats
        if enable_bench:
            print("\n" + "OPTIMIZATION METRICS")
            print(f"{'LTF Candles':25s}: {len(ltf_candles)}")
            print(f"{'LTF Zones Detected':25s}: {len(ltf_zones)}")
            print(f"{'HTF Zones Detected':25s}: {len(htf_zones)}")
            print(f"{'Candidates Scored':25s}: {funnel.candidates_scored}")
            print(f"{'Orders Placed':25s}: {funnel.orders_placed}")
            print(f"{'Orders Filled':25s}: {funnel.orders_filled}")
            scoring_rate = funnel.candidates_scored / len(ltf_candles) if ltf_candles else 0
            print(f"{'Candidates/Candle Ratio':25s}: {scoring_rate:.4f}")
        
        print("=" * 80 + "\n")
    
    # Update funnel with polarity flip metrics
    funnel.total_flips = total_flips
    funnel.flips_supply_to_demand = flips_supply_to_demand
    funnel.flips_demand_to_supply = flips_demand_to_supply
    
    return trades, zone_dicts, orders_list, capital, equity_curve, funnel


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
        # Load candles for all timeframes (HTF, ITF, LTF)
        candles_by_tf = load_candles_mtf_from_config(symbol, config)
        ltf_candles = candles_by_tf['ltf']
        
        # Execute backtest with MTF data
        trades, zones, orders, final_capital, equity_curve, funnel = execute_backtest_for_symbol(
            symbol,
            candles_by_tf,
            params,
            initial_capital
        )
        
        # Calculate max drawdown
        max_drawdown = calculate_max_drawdown(equity_curve)
        
        # Build data provenance (use LTF for provenance)
        data_provenance = {
            'first_timestamp': ltf_candles[0]['timestamp'].isoformat() if ltf_candles else None,
            'last_timestamp': ltf_candles[-1]['timestamp'].isoformat() if ltf_candles else None,
            'first_close': ltf_candles[0]['close'] if ltf_candles else None,
            'last_close': ltf_candles[-1]['close'] if ltf_candles else None,
            'candle_count_ltf': len(ltf_candles),
            'candle_count_itf': len(candles_by_tf['itf']),
            'candle_count_htf': len(candles_by_tf['htf']),
            'checksum_ltf': calculate_candle_checksum(ltf_candles),
            # Add timeframe labels for clarity
            'timeframe_ltf': config['timeframes']['ltf'],
            'timeframe_itf': config['timeframes']['itf'],
            'timeframe_htf': config['timeframes']['htf'],
            # For synthetic data, used window equals available window
            'used_first_ts': ltf_candles[0]['timestamp'].isoformat() if ltf_candles else None,
            'used_last_ts': ltf_candles[-1]['timestamp'].isoformat() if ltf_candles else None,
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
        
        # Store trades, zones, and orders on the result for later aggregation
        # We need to attach them as attributes for collection
        symbol_result.trades = trades
        symbol_result.zones = zones
        symbol_result.orders = orders
        
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
        error_result.orders = []
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


def run_backtest_experiment(config_path: str = None, config: Dict[str, Any] = None) -> ExperimentResult:
    """Run a complete backtest experiment and generate artifacts
    
    Main entry point for running experiments. Loads config, executes backtests
    across all symbols, validates integrity, and writes artifacts.
    
    Args:
        config_path: Path to YAML configuration file (optional if config provided)
        config: Configuration dictionary (optional if config_path provided)
    
    Returns:
        ExperimentResult with all data and artifacts
    """
    # Load configuration
    if config is None and config_path is None:
        raise ValueError("Either config_path or config must be provided")
    
    if config is None:
        config = load_config(config_path)
    
    # Store the config path for manifest (if provided)
    if config_path is None:
        config_path = config.get('_config_path', 'in-memory-config')
    
    
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
        # RTF refinement configuration (with defaults)
        rtf_refinement_enabled=config.get('rtf_refinement', {}).get('enabled', False),
        rtf_refinement_rule=config.get('rtf_refinement', {}).get('rule', 'engulfing'),
        rtf_refinement_lookback=config.get('rtf_refinement', {}).get('lookback', 2),
        # RTF rejection parameters (with defaults matching current behavior)
        rejection_min_wick_ratio=config.get('rtf_refinement', {}).get('rejection_params', {}).get('min_wick_ratio', 0.40),
        rejection_max_body_ratio=config.get('rtf_refinement', {}).get('rejection_params', {}).get('max_body_ratio', 0.50),
        rejection_require_close_in_direction=config.get('rtf_refinement', {}).get('rejection_params', {}).get('require_close_in_direction', True),
        rejection_require_touch_zone=config.get('rtf_refinement', {}).get('rejection_params', {}).get('require_touch_zone', True),
        # Zone attempt tracking configuration (with defaults)
        max_attempts_per_zone=config.get('zone_attempts', {}).get('max_attempts', 1),
        cooldown_bars=config.get('zone_attempts', {}).get('cooldown_bars', None),
    )
    
    # Validate timeframe hierarchy: RTF must be lower than LTF
    validate_timeframe_hierarchy(params.ltf_tf, params.rtf_tf)
    
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
    
    # FAIL FAST: Check for errors in symbol results before proceeding
    failed_symbols = []
    for result in symbol_results:
        if hasattr(result, 'error'):
            failed_symbols.append({
                'symbol': result.symbol,
                'error': result.error,
                'error_type': result.data_provenance.get('error_type', 'Unknown')
            })
    
    if failed_symbols:
        error_summary = "\n".join([
            f"  - {s['symbol']}: {s['error_type']} - {s['error']}"
            for s in failed_symbols
        ])
        raise RuntimeError(
            f"Backtest failed for {len(failed_symbols)} symbol(s):\n{error_summary}\n\n"
            f"Cannot proceed with 0 zones/orders. Fix data loading issues above."
        )
    
    # Extract trades, zones, and orders from results
    all_trades = []
    all_zones = []
    all_orders = []
    decision_funnels = []
    
    # Collect window metadata for reporting
    used_window_global_start = None
    used_window_global_end = None
    
    for result in symbol_results:
        # Extract trades, zones, and orders (attached by run_symbol_backtest)
        if hasattr(result, 'trades'):
            all_trades.extend(result.trades)
        if hasattr(result, 'zones'):
            all_zones.extend(result.zones)
        if hasattr(result, 'orders'):
            all_orders.extend(result.orders)
        
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
    
    # Sort trades, zones, and orders for determinism
    # Sort trades by (symbol, entry_idx)
    all_trades.sort(key=lambda t: (t['symbol'], t.get('entry_idx', 0)))
    
    # Sort zones by (symbol, created_at)
    all_zones.sort(key=lambda z: (z['symbol'], z.get('created_at', 0)))
    
    # Sort orders by (symbol, placed_idx)
    all_orders.sort(key=lambda o: (o['symbol'], o.get('placed_idx', 0)))
    
    # Compute order status counts for run_manifest
    order_status_counts = {
        'total': len(all_orders),
        'placed': sum(1 for o in all_orders if o['status'] == 'PLACED'),
        'filled': sum(1 for o in all_orders if o['status'] == 'FILLED'),
        'expired': sum(1 for o in all_orders if o['status'] == 'EXPIRED'),
        'cancelled': sum(1 for o in all_orders if o['status'] == 'CANCELLED'),
    }
    
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
    symbol_candle_counts = {}
    for sr in symbol_results:
        symbol_data_provenance[sr.symbol] = sr.data_provenance
        # Extract candle counts for easy debugging
        symbol_candle_counts[sr.symbol] = {
            params.ltf_tf: sr.data_provenance.get('candle_count_ltf', 0),
            params.itf_tf: sr.data_provenance.get('candle_count_itf', 0),
            params.htf_tf: sr.data_provenance.get('candle_count_htf', 0),
        }
    
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
        # Multi-timeframe configuration
        'candles_timeframes_used': {
            'ltf': params.ltf_tf,  # Lower timeframe for zone detection and entries
            'itf': params.itf_tf,  # Intermediate timeframe for trend analysis
            'htf': params.htf_tf,  # Higher timeframe for curve analysis
        },
        'candle_timeframe': params.ltf_tf,  # Legacy field for backward compatibility
        'symbol_data_provenance': symbol_data_provenance,
        'symbol_candle_counts': symbol_candle_counts,  # Per-symbol candle counts for debugging
        # Order status counts (for validation)
        'order_status_counts': order_status_counts,
    }
    
    # Add data_generation info for synthetic data
    if data_generation_info:
        run_manifest['data_generation'] = data_generation_info
    
    return ExperimentResult(
        config=config,
        symbol_results=symbol_results,
        all_trades=all_trades,
        all_zones=all_zones,
        all_orders=all_orders,
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
                'exit_reason', 'score', 'curve_state', 'trend_state',
                'zone_created_at', 'pnl', 'position_size'
            ]
            writer = csv.DictWriter(f, fieldnames=expected_columns)
            writer.writeheader()
    
    # Write zones.csv (always create file, even if empty)
    zones_file = artifacts_dir / 'zones.csv'
    with open(zones_file, 'w', newline='') as f:
        if result.all_zones:
            fieldnames = sorted(result.all_zones[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.all_zones)
        else:
            # Write header only with expected columns
            expected_columns = [
                'symbol', 'zone_type', 'proximal', 'distal',
                'created_at', 'base_len', 'legout_len', 'legout_return',
                'freshness_touches', 'first_touch_idx', 'ever_touched', 
                'final_is_fresh', 'is_fresh',  # is_fresh kept for backward compat
                'original_type', 'final_polarity_type', 'flip_count', 'last_flip_idx',
                'attempts', 'last_attempt_idx', 'disabled'  # Attempt tracking fields
            ]
            writer = csv.DictWriter(f, fieldnames=expected_columns)
            writer.writeheader()
    
    # Write orders.csv (always create file, even if empty)
    orders_file = artifacts_dir / 'orders.csv'
    with open(orders_file, 'w', newline='') as f:
        if result.all_orders:
            # Get all possible fieldnames
            fieldnames = set()
            for order in result.all_orders:
                fieldnames.update(order.keys())
            fieldnames = sorted(fieldnames)
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.all_orders)
        else:
            # Write header only with expected columns
            expected_columns = [
                'symbol', 'side', 'zone_id', 'placed_idx', 'placed_time',
                'limit_price', 'stop', 'target', 'planned_r', 'ttl_bars', 'expiry_idx',
                'status', 'filled_idx', 'filled_time', 'fill_price', 'cancel_reason'
            ]
            writer = csv.DictWriter(f, fieldnames=expected_columns)
            writer.writeheader()
    
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
            # MTF-specific metrics
            'zones_detected_ltf': sum(f.zones_detected_ltf for f in result.decision_funnels),
            'zones_detected_htf': sum(f.zones_detected_htf for f in result.decision_funnels),
            'zones_fresh_ltf': sum(f.zones_fresh_ltf for f in result.decision_funnels),
            'zones_fresh_htf': sum(f.zones_fresh_htf for f in result.decision_funnels),
            'zones_fresh_final': sum(f.zones_fresh_final for f in result.decision_funnels),
            
            # === PR REQUIREMENT A: Explicit CSV-based fresh counts ===
            'zones_fresh_csv': sum(f.zones_fresh_csv for f in result.decision_funnels),
            'zones_fresh_final_csv': sum(f.zones_fresh_final_csv for f in result.decision_funnels),
            'zones_active_fresh_end': sum(f.zones_active_fresh_end for f in result.decision_funnels),
            
            'rejected_curve': sum(f.rejected_curve for f in result.decision_funnels),
            'rejected_trend': sum(f.rejected_trend for f in result.decision_funnels),
            'candidates_scored': sum(f.candidates_scored for f in result.decision_funnels),
            'rejected_min_setup_score': sum(f.rejected_min_setup_score for f in result.decision_funnels),
            'rejected_min_reward_risk': sum(f.rejected_min_reward_risk for f in result.decision_funnels),
            'rejected_proximity': sum(f.rejected_proximity for f in result.decision_funnels),
            'refinement_attempts': sum(f.refinement_attempts for f in result.decision_funnels),
            'refinement_pass': sum(f.refinement_pass for f in result.decision_funnels),
            'refinement_fail': sum(f.refinement_fail for f in result.decision_funnels),
            
            # === PR REQUIREMENT C: Refinement failure reasons ===
            'refinement_fail_rejection_rule': sum(f.refinement_fail_rejection_rule for f in result.decision_funnels),
            'refinement_fail_insufficient_candles': sum(f.refinement_fail_insufficient_candles for f in result.decision_funnels),
            'refinement_fail_wrong_side': sum(f.refinement_fail_wrong_side for f in result.decision_funnels),
            
            'zones_attempted': sum(f.zones_attempted for f in result.decision_funnels),
            'zones_disabled_by_attempts': sum(f.zones_disabled_by_attempts for f in result.decision_funnels),
            'orders_placed': sum(f.orders_placed for f in result.decision_funnels),
            'orders_filled': sum(f.orders_filled for f in result.decision_funnels),
            'orders_expired_ttl': sum(f.orders_expired_ttl for f in result.decision_funnels),
            'trades_closed': sum(f.trades_closed for f in result.decision_funnels),
            # Polarity flip metrics
            'total_flips': sum(f.total_flips for f in result.decision_funnels),
            'flips_supply_to_demand': sum(f.flips_supply_to_demand for f in result.decision_funnels),
            'flips_demand_to_supply': sum(f.flips_demand_to_supply for f in result.decision_funnels),
            # Legacy fields for backward compatibility
            'zones_detected': sum(f.zones_detected for f in result.decision_funnels),
            'zones_fresh': sum(f.zones_fresh for f in result.decision_funnels),
            'zones_after_curve_filter': sum(f.zones_after_curve_filter for f in result.decision_funnels),
            'zones_after_trend_filter': sum(f.zones_after_trend_filter for f in result.decision_funnels),
        }
    }
    with open(artifacts_dir / 'decision_funnel.json', 'w') as f:
        json.dump(funnel_data, f, indent=2)
    
    # Console debug summary: Orders and trades per symbol
    print("\n" + "=" * 80)
    print("ORDERS & TRADES DEBUG SUMMARY (Per Symbol)")
    print("=" * 80)
    for sr in result.symbol_results:
        symbol_orders = [o for o in result.all_orders if o['symbol'] == sr.symbol]
        symbol_trades = [t for t in result.all_trades if t['symbol'] == sr.symbol]
        
        orders_placed = len(symbol_orders)
        orders_filled = len([o for o in symbol_orders if o['status'] == 'FILLED'])
        orders_expired = len([o for o in symbol_orders if o['status'] == 'EXPIRED'])
        trades_filled = len([t for t in symbol_trades if t['realized_R'] is not None])
        trades_closed = trades_filled  # All filled trades are closed
        
        print(f"{sr.symbol:10s} | orders: {orders_placed:2d} placed, {orders_filled:2d} filled, {orders_expired:2d} expired | "
              f"trades: {trades_filled:2d} filled, {trades_closed:2d} closed")
    print("=" * 80)
    
    # Print per-symbol compact decision funnel table
    print("\n" + "=" * 80)
    print("DECISION FUNNEL (Per Symbol)")
    print("=" * 80)
    for f in result.decision_funnels:
        # Format: BTCUSDT | zones 3358 → fresh 32 → curve 9 → trend 4 → score 2 → RR 0 → orders 0
        curve_part = f"curve {f.zones_after_curve_filter} → " if f.zones_after_curve_filter > 0 else ""
        trend_part = f"trend {f.zones_after_trend_filter} → " if f.zones_after_trend_filter > 0 else ""
        print(f"{f.symbol:10s} | zones {f.zones_detected:4d} → fresh {f.zones_fresh:3d} → "
              f"{curve_part}{trend_part}"
              f"score {f.candidates_scored:3d} → RR {f.rejected_min_reward_risk:3d} → "
              f"orders {f.orders_placed:3d}")
    
    # Print aggregate decision funnel
    print("\n" + "=" * 80)
    print("DECISION FUNNEL (Aggregate)")
    print("=" * 80)
    agg = funnel_data['aggregate']
    print(f"Zones Detected:              {agg['zones_detected']}")
    print(f"  ├─ Fresh at START:         {agg['zones_fresh_ltf']}")
    print(f"  └─ Fresh at END:           {agg['zones_fresh_final']}")
    if agg['zones_after_curve_filter'] > 0:
        print(f"  └─ After Curve Filter:     {agg['zones_after_curve_filter']}")
    if agg['zones_after_trend_filter'] > 0:
        print(f"  └─ After Trend Filter:     {agg['zones_after_trend_filter']}")
    print(f"Candidates Scored:           {agg['candidates_scored']}")
    if agg['rejected_min_setup_score'] > 0:
        print(f"  ├─ Rejected (Min Score):   {agg['rejected_min_setup_score']}")
    if agg['rejected_min_reward_risk'] > 0:
        print(f"  ├─ Rejected (Min R:R):     {agg['rejected_min_reward_risk']}")
    if agg.get('rejected_proximity', 0) > 0:
        print(f"  ├─ Rejected (Proximity):   {agg['rejected_proximity']}")
    if agg.get('refinement_attempts', 0) > 0:
        print(f"  ├─ Refinement Attempts:    {agg['refinement_attempts']}")
        print(f"  │  ├─ Passed:              {agg['refinement_pass']}")
        print(f"  │  └─ Failed:              {agg['refinement_fail']}")
    if agg.get('zones_attempted', 0) > 0:
        print(f"  ├─ Zones Attempted:        {agg['zones_attempted']}")
    if agg.get('zones_disabled_by_attempts', 0) > 0:
        print(f"  ├─ Zones Disabled (Max):   {agg['zones_disabled_by_attempts']}")
    print(f"Orders Placed:               {agg['orders_placed']}")
    print(f"  ├─ Filled:                 {agg['orders_filled']}")
    print(f"  └─ Expired (TTL):          {agg['orders_expired_ttl']}")
    print(f"Trades Closed:               {agg['trades_closed']}")
    print("=" * 80)
    
    # Validate order status counts match funnel
    order_status_counts = result.run_manifest.get('order_status_counts', {})
    print("\n" + "=" * 80)
    print("ORDER STATUS VALIDATION")
    print("=" * 80)
    print(f"From orders.csv:             Total: {order_status_counts.get('total', 0)}, "
          f"Filled: {order_status_counts.get('filled', 0)}, "
          f"Expired: {order_status_counts.get('expired', 0)}, "
          f"Pending: {order_status_counts.get('placed', 0)}")
    print(f"From decision_funnel.json:   Placed: {agg['orders_placed']}, "
          f"Filled: {agg['orders_filled']}, "
          f"Expired: {agg['orders_expired_ttl']}")
    
    # Check for consistency
    funnel_matches = (
        order_status_counts.get('total', 0) == agg['orders_placed'] and
        order_status_counts.get('filled', 0) == agg['orders_filled'] and
        order_status_counts.get('expired', 0) == agg['orders_expired_ttl']
    )
    if funnel_matches:
        print("✅ Order status counts MATCH between orders.csv and decision_funnel.json")
    else:
        print("⚠️  WARNING: Order status counts DO NOT MATCH!")
    print("=" * 80)
    
    print(f"\nArtifacts written to: {artifacts_dir}")
    print(f"  - summary.json ({len(result.symbol_results)} symbols)")
    print(f"  - trades.csv ({len(result.all_trades)} trades)")
    print(f"  - zones.csv ({len(result.all_zones)} zones)")
    print(f"  - orders.csv ({len(result.all_orders)} orders)")
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
