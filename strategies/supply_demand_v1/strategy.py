"""Supply and Demand Trading Strategy - Execution Layer

This module provides backward compatibility by re-exporting framework-agnostic
strategy logic from strategy_core.py and adding execution-specific functions.

Execution-specific logic:
- Fill simulation (check_limit_order_fill)
- Position management (manage_trade_plan, check_intrabar_exit)
- PnL calculation (calculate_pnl_with_costs)
- Trading costs (calculate_trading_costs)
- Framework interface (create_strategy_universe, create_indicators, decide_trades)
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum

# Re-export everything from strategy_core for backward compatibility
from .strategy_core import *

# Explicitly list what we're exporting for clarity
from .strategy_core import (
    # Enums
    CurveLocation, TrendDirection, ZoneType, EntryMode, OrderState,
    # Data classes
    SupplyDemandParameters, Zone, TradePlan,
    # Zone detection
    identify_boring_candles, identify_exciting_candles,
    detect_zones_dbr_rbd, compute_zone_lines_proximal_distal,
    # Freshness
    is_zone_fresh,
    # Multi-timeframe
    find_nearest_fresh_zones_htf, curve_location, trend_direction_itf,
    detect_pivot_highs_lows, detect_pivot_highs_lows_bounded,
    find_nearest_fresh_supply_above, find_nearest_fresh_demand_below,
    classify_curve, classify_trend,
    # Gating
    should_allow_trade,
    # Scoring
    odds_enhancer_score,
    # Trade planning
    build_trade_plan, position_size,
    # Utility
    calculate_body_and_range, calculate_r_multiple,
)

class CurveLocation(Enum):
    """Price location within the HTF range"""
    HIGH = "high"
    EQUILIBRIUM = "equilibrium"
    LOW = "low"


class TrendDirection(Enum):
    """Trend direction on ITF"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


class ZoneType(Enum):
    """Type of supply/demand zone"""
    DEMAND = "demand"  # Drop-Base-Rally (DBR)
    SUPPLY = "supply"  # Rally-Base-Drop (RBD)


class EntryMode(Enum):
    """Entry execution mode"""
    LIMIT = "limit"  # Place limit order at proximal
    CONFIRMATION = "confirmation"  # Wait for price to reverse through proximal


class OrderState(Enum):
    """Order state for limit orders"""
    PENDING = "pending"  # Order placed but not filled
    FILLED = "filled"  # Order filled
    CANCELLED = "cancelled"  # Order cancelled (TTL expired)


@dataclass
class SupplyDemandParameters:
    """Configuration parameters for Supply and Demand strategy
    
    All parameters are based on the specifications in TradingStrategySpec.md.
    """
    
    # Candle Classification
    # Note: These thresholds are complementary - a candle is boring if body <= threshold,
    # and exciting if body > threshold. The same value creates a clear boundary.
    boring_body_ratio: float = 0.50  # body <= 50% of range = boring
    exciting_body_ratio: float = 0.50  # body > 50% of range = exciting
    
    # Zone Detection
    min_base_candles: int = 1
    max_base_candles: int = 6  # For optimal scoring
    min_legout_candles: int = 1
    
    # Proximal Line Placement
    proximal_mode: str = "body"  # "body" or "wick"
    
    # Scoring Thresholds
    min_setup_score: float = 6.0  # Minimum total score to take trade
    freshness_touches_best: int = 0  # Fresh zone = 3 points
    freshness_touches_good: int = 1  # 1 touch = 1.5 points
    base_time_best: int = 3  # ≤3 candles = 2 points
    base_time_good: int = 6  # 4-6 candles = 1 point
    legout_strength_high_threshold: float = 0.10  # 10% return = 2 points
    legout_strength_mid_threshold: float = 0.05  # 5% return = 1 point
    
    # Trade Management
    risk_pct: float = 0.02  # 2% of account per trade
    breakeven_at_r: float = 2.0  # Move stop to BE at 2R
    take_profit_at_r: float = 3.0  # Close position at 3R
    min_reward_risk: float = 3.0  # Minimum R:R to consider trade
    stop_buffer_pct: float = 0.001  # Buffer beyond distal for stop (0.1%)
    
    # Multi-Timeframe Configuration
    htf_tf: str = "4h"  # Higher timeframe for curve analysis
    itf_tf: str = "1h"  # Intermediate timeframe for trend
    ltf_tf: str = "15m"  # Lower timeframe for zones and entry
    rtf_tf: Optional[str] = "5m"  # Refining timeframe (optional)
    
    # Trend Detection
    pivot_len: int = 5  # Lookback period for pivot detection
    pivots_to_consider: int = 4  # Number of pivots to analyze for trend
    
    # Multi-Timeframe Gating (Curve + Trend)
    allow_eq_trades: bool = True  # Allow trades when curve is in EQUILIBRIUM
    eq_requires_trend_alignment: bool = True  # Require trend alignment for EQ trades
    eq_min_setup_score_bonus: float = 1.0  # Bonus score required for EQ trades
    
    # Entry Mode
    entry_mode: EntryMode = EntryMode.LIMIT  # LIMIT or CONFIRMATION
    
    # Trading Costs
    fees_bps: float = 10.0  # Trading fees in basis points (default 10 bps = 0.1%)
    slippage_bps: float = 5.0  # Slippage in basis points (default 5 bps = 0.05%)
    
    # Limit Order Configuration
    ttl_bars: Optional[int] = 10  # Time-to-live in bars for limit orders (None = no expiry)
    
    # Order Deduplication & Retry Policy
    max_retries_per_zone: int = 1  # Maximum order placement attempts per zone (default 1 = no retries)
    rearm_requires_price_reset: bool = True  # Require price to move away from zone before retry
    rearm_price_buffer_pct: float = 0.005  # Price must move beyond proximal + 0.5% to rearm


@dataclass
class Zone:
    """Represents a supply or demand zone
    
    Attributes:
        zone_type: SUPPLY or DEMAND (original detection type - IMMUTABLE)
        proximal: Price level closest to current price (entry reference)
        distal: Price level farthest from current price (stop reference)
        created_at: Index where zone was created (legout_end_idx)
        created_time: Optional timestamp when zone was created
        base_start_idx: Index where base begins
        base_end_idx: Index where base ends
        legout_end_idx: Index where leg-out ends
        base_len: Number of candles in the base
        legout_len: Number of candles in the leg-out
        freshness_touches: Number of times price returned to zone after creation
        legout_return: Percentage return of the leg-out move
        first_touch_idx: Index when zone was first touched (None if never touched)
        ever_touched: Whether zone was EVER touched (final state, NOT time-relative)
        last_checked_idx: Last candle index where freshness was checked (for incremental updates)
        
        POLARITY FIELDS (for dynamic supply/demand flipping):
        original_type: SUPPLY or DEMAND (same as zone_type, kept for clarity)
        polarity_type: SUPPLY or DEMAND (mutable, changes based on price breaks)
        flip_count: Number of times polarity has flipped
        last_flip_idx: Index of most recent polarity flip (None if never flipped)
        last_polarity_check_idx: Last index where polarity was checked
        
        DEPRECATED FIELDS (for backward compatibility):
        is_fresh: DEPRECATED - Use is_zone_fresh_at_idx() instead for time-relative freshness
    """
    zone_type: ZoneType
    proximal: float
    distal: float
    created_at: int
    base_start_idx: int
    base_end_idx: int
    legout_end_idx: int
    base_len: int
    legout_len: int
    created_time: Optional[Any] = None
    freshness_touches: int = 0
    legout_return: float = 0.0
    # Time-relative freshness fields
    first_touch_idx: Optional[int] = None  # Index when first touched (None = never)
    ever_touched: bool = False  # Final state: was zone ever touched?
    last_checked_idx: int = -1  # Track last checked index for incremental updates
    # DEPRECATED: Use is_zone_fresh_at_idx() for time-relative freshness
    is_fresh: bool = True  # Kept for backward compatibility only
    # Polarity fields (dynamic zone type)
    original_type: Optional[ZoneType] = None  # Set during initialization
    polarity_type: Optional[ZoneType] = None  # Current polarity (changes over time)
    flip_count: int = 0  # Number of times polarity flipped
    last_flip_idx: Optional[int] = None  # Index of most recent flip
    last_polarity_check_idx: int = -1  # Last index where polarity was updated


def initialize_zone_polarity(zone: Zone) -> None:
    """Initialize polarity fields for a newly created zone
    
    Sets original_type and polarity_type to the detected zone_type.
    Called once when zone is first created.
    
    Args:
        zone: Zone object to initialize
    
    Side effects:
        Sets zone.original_type and zone.polarity_type
    """
    if zone.original_type is None:
        zone.original_type = zone.zone_type
    if zone.polarity_type is None:
        zone.polarity_type = zone.zone_type


def check_polarity_flip(
    zone: Zone,
    current_idx: int,
    current_close: float,
    prev_close: float
) -> bool:
    """Check if zone polarity should flip based on price crossing distal boundary
    
    Uses conservative "decisive break" rule with hysteresis:
    - Supply→Demand flip: previous close <= distal AND current close > distal
    - Demand→Supply flip: previous close >= distal AND current close < distal
    
    Args:
        zone: Zone to check
        current_idx: Current candle index
        current_close: Current candle close price
        prev_close: Previous candle close price
    
    Returns:
        True if polarity flipped, False otherwise
    
    Side effects:
        Updates zone.polarity_type, zone.flip_count, zone.last_flip_idx if flip occurs
    """
    # Skip if already checked at this index
    if zone.last_polarity_check_idx >= current_idx:
        return False
    
    zone.last_polarity_check_idx = current_idx
    
    # Get current polarity (use zone_type if polarity_type not initialized)
    current_polarity = zone.polarity_type if zone.polarity_type is not None else zone.zone_type
    
    # Use distal as flip boundary (most conservative)
    flip_boundary = zone.distal
    
    flipped = False
    
    if current_polarity == ZoneType.SUPPLY:
        # Supply flips to Demand when price decisively breaks ABOVE distal
        if prev_close <= flip_boundary and current_close > flip_boundary:
            zone.polarity_type = ZoneType.DEMAND
            zone.flip_count += 1
            zone.last_flip_idx = current_idx
            flipped = True
    elif current_polarity == ZoneType.DEMAND:
        # Demand flips to Supply when price decisively breaks BELOW distal
        if prev_close >= flip_boundary and current_close < flip_boundary:
            zone.polarity_type = ZoneType.SUPPLY
            zone.flip_count += 1
            zone.last_flip_idx = current_idx
            flipped = True
    
    return flipped


def get_zone_polarity_at_idx(zone: Zone, idx: int) -> ZoneType:
    """Get the polarity of a zone at a specific index
    
    Returns the polarity type that should be used for trading decisions at the given index.
    If polarity hasn't been initialized or updated yet, returns the original zone_type.
    
    Args:
        zone: Zone object
        idx: Candle index
    
    Returns:
        Current polarity type (SUPPLY or DEMAND)
    """
    # If polarity never initialized, use original type
    if zone.polarity_type is None:
        return zone.zone_type
    
    # If there have been flips and the requested idx is at or after the last flip,
    # use the current polarity_type
    if zone.last_flip_idx is not None and idx >= zone.last_flip_idx:
        return zone.polarity_type
    
    # If we've checked polarity up to this index (but no flip yet), use polarity_type
    if zone.last_polarity_check_idx >= idx:
        return zone.polarity_type
    
    # Otherwise, use original type (polarity not updated yet to this point)
    return zone.zone_type


@dataclass
class TradePlan:
    """Complete trade plan with SET (Stop, Entry, Target)
    
    Attributes:
        zone: The zone this trade is based on
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Initial profit target
        position_size: Number of units to trade
        risk_amount: Dollar amount at risk
        reward_amount: Dollar amount of potential profit
        r_multiple: Reward-to-risk ratio
        score: Odds enhancer total score
        order_state: Current state of the limit order (PENDING, FILLED, CANCELLED)
        placed_at_idx: Candle index when order was placed
        filled_at_idx: Candle index when order was filled (None if not filled)
        actual_entry_price: Actual entry price after fees and slippage
        entry_cost: Total cost of entry (fees + slippage)
        exit_cost: Total cost of exit (fees + slippage)
    """
    zone: Zone
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    reward_amount: float
    r_multiple: float
    score: float
    order_state: OrderState = OrderState.PENDING
    placed_at_idx: Optional[int] = None
    filled_at_idx: Optional[int] = None
    actual_entry_price: Optional[float] = None
    entry_cost: float = 0.0
    exit_cost: float = 0.0
    reward_amount: float
    r_multiple: float
    score: float


# ============================================================================
# Trading Strategy Framework Interface Functions
# ============================================================================

def create_strategy_universe(
    universe_options: Dict[str, Any]
) -> Any:
    """Create the trading universe for the strategy
    
    Defines which trading pairs/assets the strategy will trade.
    This follows the Trading Strategy framework pattern.
    
    Args:
        universe_options: Configuration for universe creation including
            exchange, pairs, timeframes, etc.
    
    Returns:
        Trading universe object compatible with Trading Strategy framework
    
    Note:
        Business logic to be implemented in future PR.
    """
    # TODO: Implement universe creation
    # - Define crypto pairs to trade (e.g., BTC/USDT, ETH/USDT)
    # - Set up data feeds for multiple timeframes (HTF, ITF, LTF)
    # - Configure exchange and market type
    raise NotImplementedError("Universe creation to be implemented")


def create_indicators(
    parameters: SupplyDemandParameters
) -> Dict[str, Any]:
    """Create and configure technical indicators
    
    Sets up any technical indicators needed for the strategy beyond
    the core price action analysis. May include moving averages for
    trend confirmation, ATR for volatility, etc.
    
    Args:
        parameters: Strategy parameters
    
    Returns:
        Dictionary of indicator configurations
    
    Note:
        Business logic to be implemented in future PR.
    """
    # TODO: Implement indicator setup
    # - Configure any supporting indicators (optional for v1)
    # - Set up multi-timeframe data structure
    # - Initialize zone tracking structures
    raise NotImplementedError("Indicator creation to be implemented")


def decide_trades(
    timestamp: Any,
    parameters: SupplyDemandParameters,
    state: Any,
    pricing_model: Any
) -> List[Any]:
    """Main decision function - evaluate zones and generate trade signals
    
    This is the core decision function called by the Trading Strategy framework
    on each decision cycle. It orchestrates all analysis and trade decisions.
    
    Args:
        timestamp: Current timestamp
        parameters: Strategy parameters
        state: Current strategy state (portfolio, positions, etc.)
        pricing_model: Pricing model for execution
    
    Returns:
        List of trade objects (buy/sell/close signals)
    
    Note:
        Business logic to be implemented in future PR.
    """
    # TODO: Implement main trading logic
    # 1. Update zone tracking (detect new zones, update freshness)
    # 2. Analyze curve location (HTF)
    # 3. Analyze trend direction (ITF)
    # 4. Score active zones using odds enhancers
    # 5. Generate trade plans for qualified setups
    # 6. Manage existing positions (move stops, take profits)
    # 7. Return trade signals
    raise NotImplementedError("Trade decision logic to be implemented")


# ============================================================================
# Candle Analysis Functions
# ============================================================================

def identify_boring_candles(
    candles: Any,
    body_ratio: float = 0.50
) -> List[bool]:
    """Identify boring (consolidation) candles
    
    A boring candle indicates supply/demand balance and potential accumulation.
    
    Args:
        candles: OHLC candle data (list of dicts or DataFrame)
        body_ratio: Maximum body-to-range ratio for boring classification
    
    Returns:
        List of boolean flags indicating which candles are boring
    
    Rule:
        body <= body_ratio * range, where:
        - body = abs(close - open)
        - range = high - low
    """
    result = []
    for candle in candles:
        body, range_val = calculate_body_and_range(candle)
        # Avoid division by zero for doji candles with no range
        if range_val == 0:
            is_boring = True  # Treat as boring if no range
        else:
            is_boring = body <= body_ratio * range_val
        result.append(is_boring)
    return result


def identify_exciting_candles(
    candles: Any,
    body_ratio: float = 0.50
) -> List[bool]:
    """Identify exciting (momentum) candles
    
    An exciting candle indicates strong imbalance and institutional activity.
    
    Args:
        candles: OHLC candle data (list of dicts or DataFrame)
        body_ratio: Minimum body-to-range ratio for exciting classification
    
    Returns:
        List of boolean flags indicating which candles are exciting
    
    Rule:
        body > body_ratio * range
    """
    result = []
    for candle in candles:
        body, range_val = calculate_body_and_range(candle)
        # Avoid division by zero for doji candles with no range
        if range_val == 0:
            is_exciting = False  # Treat as not exciting if no range
        else:
            is_exciting = body > body_ratio * range_val
        result.append(is_exciting)
    return result


# ============================================================================
# Zone Detection Functions
# ============================================================================

def detect_zones_dbr_rbd(
    candles: Any,
    parameters: SupplyDemandParameters
) -> List[Zone]:
    """Detect Drop-Base-Rally (demand) and Rally-Base-Drop (supply) zones
    
    Identifies the three-element zone structure:
    1. Leg-In: Exciting move into the base
    2. Base: One or more boring candles
    3. Leg-Out: Exciting move out of the base
    
    Args:
        candles: OHLC candle data (list of dicts with 'open', 'high', 'low', 'close')
        parameters: Strategy parameters for zone detection
    
    Returns:
        List of detected zones (both supply and demand)
    """
    if len(candles) < 3:
        return []
    
    # Classify all candles
    boring = identify_boring_candles(candles, parameters.boring_body_ratio)
    exciting = identify_exciting_candles(candles, parameters.exciting_body_ratio)
    
    zones = []
    i = 0
    
    while i < len(candles) - 2:
        # Look for pattern: exciting -> boring(s) -> exciting
        if not exciting[i]:
            i += 1
            continue
        
        # Found potential leg-in (exciting candle)
        legin_idx = i
        
        # Check for base (boring candles)
        base_start = i + 1
        base_end = base_start
        
        # Scan for consecutive boring candles
        while base_end < len(candles) and boring[base_end]:
            base_end += 1
        
        base_len = base_end - base_start
        
        # Validate base length
        if base_len < parameters.min_base_candles:
            i += 1
            continue
        
        # Check for leg-out (exciting candles after base)
        legout_start = base_end
        legout_end = legout_start
        
        # Scan for consecutive exciting candles that move in the same direction
        # Get the first leg-out candle to determine direction
        if legout_start >= len(candles) or not exciting[legout_start]:
            i += 1
            continue
        
        first_legout = candles[legout_start]
        first_legout_direction = first_legout['close'] - first_legout['open']  # Positive = bullish, negative = bearish
        
        # Scan for consecutive exciting candles moving in same direction
        while legout_end < len(candles) and exciting[legout_end]:
            candle = candles[legout_end]
            candle_direction = candle['close'] - candle['open']
            
            # Check if candle moves in the same direction as first leg-out candle
            # (both positive or both negative)
            if (first_legout_direction > 0 and candle_direction > 0) or \
               (first_legout_direction < 0 and candle_direction < 0):
                legout_end += 1
            else:
                # Direction changed, stop leg-out here
                break
        
        legout_len = legout_end - legout_start
        
        # Validate leg-out
        if legout_len < parameters.min_legout_candles:
            i += 1
            continue
        
        # We have a valid pattern, now determine if it's DBR or RBD
        # DBR: price drops (leg-in), consolidates (base), then rallies (leg-out)
        # RBD: price rallies (leg-in), consolidates (base), then drops (leg-out)
        
        legin_candle = candles[legin_idx]
        legout_first_candle = candles[legout_start]
        legout_last_candle = candles[legout_end - 1]
        
        # Determine direction by comparing leg-in and leg-out movements
        legin_close = legin_candle['close']
        legin_open = legin_candle['open']
        base_first = candles[base_start]
        base_last = candles[base_end - 1]
        
        # Get base average level
        base_level = (base_first['close'] + base_last['close']) / 2
        
        # Calculate movements
        legin_move = legin_close - legin_open  # Positive = bullish, negative = bearish
        legout_close = legout_last_candle['close']
        legout_open = legout_first_candle['open']
        legout_move = legout_close - legout_open  # Positive = bullish, negative = bearish
        
        # DBR: bearish leg-in (negative), bullish leg-out (positive)
        # RBD: bullish leg-in (positive), bearish leg-out (negative)
        is_dbr = legin_move < 0 and legout_move > 0
        is_rbd = legin_move > 0 and legout_move < 0
        
        if not (is_dbr or is_rbd):
            i += 1
            continue
        
        zone_type = ZoneType.DEMAND if is_dbr else ZoneType.SUPPLY
        
        # Compute proximal and distal lines
        zone_pattern = (legin_idx, base_end - 1, legout_end - 1)
        proximal, distal = compute_zone_lines_proximal_distal(
            zone_pattern, candles, zone_type, parameters.proximal_mode
        )
        
        # Calculate leg-out return (use open to close of leg-out)
        legout_start_price = legout_first_candle['open']
        legout_end_price = legout_last_candle['close']
        if legout_start_price != 0:
            legout_return = abs(legout_end_price - legout_start_price) / legout_start_price
        else:
            legout_return = 0.0
        
        # Create zone object
        zone = Zone(
            zone_type=zone_type,
            proximal=proximal,
            distal=distal,
            created_at=legout_end - 1,
            base_start_idx=base_start,
            base_end_idx=base_end - 1,
            legout_end_idx=legout_end - 1,
            base_len=base_len,
            legout_len=legout_len,
            freshness_touches=0,
            legout_return=legout_return,
            is_fresh=True
        )
        
        # Initialize polarity fields
        initialize_zone_polarity(zone)
        
        zones.append(zone)
        
        # Move past this pattern to look for next zone
        i = legout_end
    
    return zones


def compute_zone_lines_proximal_distal(
    zone_pattern: Tuple[int, int, int],
    candles: Any,
    zone_type: ZoneType,
    proximal_mode: str = "body"
) -> Tuple[float, float]:
    """Calculate proximal and distal lines for a zone
    
    Args:
        zone_pattern: Tuple of (legin_end, base_end, legout_end) indices
        candles: OHLC candle data (list of dicts)
        zone_type: SUPPLY or DEMAND
        proximal_mode: "body" or "wick" for proximal placement
    
    Returns:
        Tuple of (proximal, distal) price levels
    
    Rules:
        Demand (DBR):
        - Proximal: Highest candle body in base
        - Distal: Lowest wick across entire pattern
        
        Supply (RBD):
        - Proximal: Lowest candle body in base
        - Distal: Highest wick across entire pattern
    """
    legin_start, base_end, legout_end = zone_pattern
    
    # Extract base candles (from start of base to end of base)
    base_start = legin_start + 1
    base_candles = candles[base_start:base_end + 1]
    
    # Extract full pattern for distal calculation
    # Pattern starts at some point before base (leg-in), includes base and leg-out
    # For simplicity, we'll use the entire zone structure available
    full_pattern = candles[legin_start:legout_end + 1]
    
    if zone_type == ZoneType.DEMAND:
        # DBR: Drop-Base-Rally
        # Proximal: Highest candle body in base
        if proximal_mode == "body":
            # Get the highest body top in base
            proximal = max(max(c['open'], c['close']) for c in base_candles)
        else:  # wick mode
            # Get the highest high in base
            proximal = max(c['high'] for c in base_candles)
        
        # Distal: Lowest low across full structure
        distal = min(c['low'] for c in full_pattern)
        
    else:  # SUPPLY
        # RBD: Rally-Base-Drop
        # Proximal: Lowest candle body in base
        if proximal_mode == "body":
            # Get the lowest body bottom in base
            proximal = min(min(c['open'], c['close']) for c in base_candles)
        else:  # wick mode
            # Get the lowest low in base
            proximal = min(c['low'] for c in base_candles)
        
        # Distal: Highest high across full structure
        distal = max(c['high'] for c in full_pattern)
    
    return proximal, distal


def is_zone_fresh(
    zone: Zone,
    candles: Any,
    current_idx: int
) -> bool:
    """Check if a zone is fresh (not revisited since creation) - OPTIMIZED
    
    This function uses incremental updates to avoid re-scanning all candles.
    It only checks candles from last_checked_idx to current_idx.
    
    Args:
        zone: Zone to check
        candles: OHLC candle data (list of dicts)
        current_idx: Current candle index
    
    Returns:
        True if zone is fresh, False otherwise
    
    Rule:
        A zone is fresh until any subsequent candle's high/low overlaps
        the zone interval [distal, proximal]
    
    Side effects:
        Updates zone.freshness_touches counter, zone.is_fresh flag, and zone.last_checked_idx
    
    Optimization:
        - Incremental: Only check new candles since last_checked_idx
        - O(1) per call instead of O(n) where n is candles since zone creation
        - Caches result: If we've already checked this index, return immediately
    """
    # Early exit: If we've already checked this index, return cached result
    if zone.last_checked_idx >= current_idx:
        return zone.is_fresh
    
    # Define zone bounds (calculate once, reuse)
    if zone.zone_type == ZoneType.DEMAND:
        # For demand zones: proximal is top, distal is bottom
        zone_top = zone.proximal
        zone_bottom = zone.distal
    else:  # SUPPLY
        # For supply zones: proximal is bottom, distal is top
        zone_top = zone.distal
        zone_bottom = zone.proximal
    
    # Determine start index for incremental check
    start_idx = max(zone.created_at + 1, zone.last_checked_idx + 1)
    end_idx = min(current_idx + 1, len(candles))
    
    # Check only NEW candles since last check
    for i in range(start_idx, end_idx):
        candle = candles[i]
        
        # Check if candle overlaps the zone
        # Overlap occurs if candle's low is below zone top AND candle's high is above zone bottom
        if candle['low'] <= zone_top and candle['high'] >= zone_bottom:
            zone.freshness_touches += 1
            zone.is_fresh = False
            # Continue counting touches (don't early exit) for consistency with tests
    
    # Update last checked index
    zone.last_checked_idx = current_idx
    
    return zone.is_fresh


# ============================================================================
# Multi-Timeframe Analysis
# ============================================================================

def find_nearest_fresh_zones_htf(
    candles: Any,
    current_price: float,
    parameters: SupplyDemandParameters
) -> Tuple[Optional[Zone], Optional[Zone]]:
    """Find nearest fresh supply zone above and demand zone below current price
    
    Used for HTF curve analysis to determine if price is high, low, or
    in equilibrium within the broader range.
    
    Args:
        candles: HTF candle data
        current_price: Current price
        parameters: Strategy parameters
    
    Returns:
        Tuple of (supply_zone_above, demand_zone_below)
        Either can be None if not found
    """
    # Detect all zones on HTF
    all_zones = detect_zones_dbr_rbd(candles, parameters)
    
    # Update freshness for all zones
    current_idx = len(candles) - 1
    for zone in all_zones:
        is_zone_fresh(zone, candles, current_idx)
    
    # Filter to fresh zones only
    fresh_zones = [z for z in all_zones if z.is_fresh]
    
    # Find nearest fresh supply above current price
    supply_above = None
    min_distance_above = float('inf')
    for zone in fresh_zones:
        if zone.zone_type == ZoneType.SUPPLY:
            # For supply zones, proximal is the lower boundary
            if zone.proximal > current_price:
                distance = zone.proximal - current_price
                if distance < min_distance_above:
                    min_distance_above = distance
                    supply_above = zone
    
    # Find nearest fresh demand below current price
    demand_below = None
    min_distance_below = float('inf')
    for zone in fresh_zones:
        if zone.zone_type == ZoneType.DEMAND:
            # For demand zones, proximal is the upper boundary
            if zone.proximal < current_price:
                distance = current_price - zone.proximal
                if distance < min_distance_below:
                    min_distance_below = distance
                    demand_below = zone
    
    return supply_above, demand_below


def curve_location(
    current_price: float,
    supply_zone_above: Optional[Zone],
    demand_zone_below: Optional[Zone]
) -> CurveLocation:
    """Determine where current price is within the HTF range
    
    Divides the range between nearest fresh supply (above) and demand (below)
    into three equal sections to determine curve location.
    
    Args:
        current_price: Current price
        supply_zone_above: Nearest fresh supply zone above price
        demand_zone_below: Nearest fresh demand zone below price
    
    Returns:
        CurveLocation (HIGH, EQUILIBRIUM, or LOW)
    
    Rule:
        - Range = supply_proximal - demand_proximal
        - Divide into thirds
        - Top third = HIGH
        - Middle third = EQUILIBRIUM
        - Bottom third = LOW
    """
    # If we don't have both zones, default to EQUILIBRIUM
    if supply_zone_above is None or demand_zone_below is None:
        return CurveLocation.EQUILIBRIUM
    
    # Get proximal lines
    supply_proximal = supply_zone_above.proximal
    demand_proximal = demand_zone_below.proximal
    
    # Calculate range and thirds
    total_range = supply_proximal - demand_proximal
    
    # If range is invalid (should not happen), default to EQUILIBRIUM
    if total_range <= 0:
        return CurveLocation.EQUILIBRIUM
    
    # Calculate thirds
    third = total_range / 3.0
    
    # Bottom third: [demand_proximal, demand_proximal + third)
    low_boundary = demand_proximal + third
    # Middle third: [demand_proximal + third, demand_proximal + 2*third)
    eq_boundary = demand_proximal + 2 * third
    # Top third: [demand_proximal + 2*third, supply_proximal]
    
    if current_price < low_boundary:
        return CurveLocation.LOW
    elif current_price < eq_boundary:
        return CurveLocation.EQUILIBRIUM
    else:
        return CurveLocation.HIGH


def trend_direction_itf(
    candles: Any,
    current_idx: int,
    parameters: SupplyDemandParameters
) -> TrendDirection:
    """Determine trend direction on ITF using pivot analysis
    
    OPTIMIZED: Uses bounded trailing window instead of slicing full history.
    Only analyzes candles needed for pivot detection (pivot_len * pivots_to_consider).
    
    Analyzes pivot highs and lows to classify trend:
    - Uptrend: Higher highs and higher lows (HH/HL)
    - Downtrend: Lower highs and lower lows (LH/LL)
    - Sideways: Mixed or equal highs/lows
    
    Args:
        candles: ITF candle data (full list, not sliced)
        current_idx: Current ITF candle index (analysis done up to this index)
        parameters: Strategy parameters (pivot_len, pivots_to_consider)
    
    Returns:
        TrendDirection (UP, DOWN, or SIDEWAYS)
    """
    # Calculate minimum window needed for trend analysis
    # Need: pivot_len candles on each side of pivot + enough pivots to analyze
    # Conservative estimate: pivot_len * 2 * pivots_to_consider * 2
    min_history = parameters.pivot_len * 2 + parameters.pivots_to_consider * parameters.pivot_len * 2
    
    if current_idx < min_history:
        return TrendDirection.SIDEWAYS
    
    # Define bounded window for pivot detection
    # Look back only as far as needed to find pivots_to_consider pivots
    window_start = max(0, current_idx - min_history - 100)  # Add buffer for reliability
    window_end = current_idx + 1  # Inclusive end
    
    # Detect pivots only in bounded window (no slicing, use indices)
    pivot_highs, pivot_lows = detect_pivot_highs_lows_bounded(
        candles, window_start, window_end, parameters.pivot_len
    )
    
    # Need at least 2 pivots of each type to determine trend
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return TrendDirection.SIDEWAYS
    
    # Get the most recent pivots (up to pivots_to_consider)
    recent_highs = pivot_highs[-parameters.pivots_to_consider:]
    recent_lows = pivot_lows[-parameters.pivots_to_consider:]
    
    # Need at least 2 pivots to compare
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return TrendDirection.SIDEWAYS
    
    # Analyze highs: are they making higher highs (HH)?
    highs_ascending = True
    for i in range(1, len(recent_highs)):
        prev_idx = recent_highs[i - 1]
        curr_idx = recent_highs[i]
        if candles[curr_idx]['high'] <= candles[prev_idx]['high']:
            highs_ascending = False
            break
    
    # Analyze highs: are they making lower highs (LH)?
    highs_descending = True
    for i in range(1, len(recent_highs)):
        prev_idx = recent_highs[i - 1]
        curr_idx = recent_highs[i]
        if candles[curr_idx]['high'] >= candles[prev_idx]['high']:
            highs_descending = False
            break
    
    # Analyze lows: are they making higher lows (HL)?
    lows_ascending = True
    for i in range(1, len(recent_lows)):
        prev_idx = recent_lows[i - 1]
        curr_idx = recent_lows[i]
        if candles[curr_idx]['low'] <= candles[prev_idx]['low']:
            lows_ascending = False
            break
    
    # Analyze lows: are they making lower lows (LL)?
    lows_descending = True
    for i in range(1, len(recent_lows)):
        prev_idx = recent_lows[i - 1]
        curr_idx = recent_lows[i]
        if candles[curr_idx]['low'] >= candles[prev_idx]['low']:
            lows_descending = False
            break
    
    # Classify trend
    # Uptrend: HH and HL
    if highs_ascending and lows_ascending:
        return TrendDirection.UP
    # Downtrend: LH and LL
    elif highs_descending and lows_descending:
        return TrendDirection.DOWN
    # Sideways: Mixed signals
    else:
        return TrendDirection.SIDEWAYS


def find_nearest_fresh_supply_above(
    current_price: float,
    zones_htf: List[Zone]
) -> Optional[Zone]:
    """Find the nearest fresh supply zone above current price
    
    Args:
        current_price: Current price
        zones_htf: List of zones detected on HTF (should include freshness updates)
    
    Returns:
        Nearest fresh supply zone above price, or None if not found
    """
    supply_above = None
    min_distance = float('inf')
    
    for zone in zones_htf:
        if zone.zone_type == ZoneType.SUPPLY and zone.is_fresh:
            # For supply zones, proximal is the lower boundary
            if zone.proximal > current_price:
                distance = zone.proximal - current_price
                if distance < min_distance:
                    min_distance = distance
                    supply_above = zone
    
    return supply_above


def find_nearest_fresh_demand_below(
    current_price: float,
    zones_htf: List[Zone]
) -> Optional[Zone]:
    """Find the nearest fresh demand zone below current price
    
    Args:
        current_price: Current price
        zones_htf: List of zones detected on HTF (should include freshness updates)
    
    Returns:
        Nearest fresh demand zone below price, or None if not found
    """
    demand_below = None
    min_distance = float('inf')
    
    for zone in zones_htf:
        if zone.zone_type == ZoneType.DEMAND and zone.is_fresh:
            # For demand zones, proximal is the upper boundary
            if zone.proximal < current_price:
                distance = current_price - zone.proximal
                if distance < min_distance:
                    min_distance = distance
                    demand_below = zone
    
    return demand_below


def classify_curve(
    current_price: float,
    supply_proximal: Optional[float],
    demand_proximal: Optional[float]
) -> str:
    """Classify curve location as "LOW", "EQ", or "HIGH"
    
    Wrapper around curve_location that returns string values for convenience.
    
    Args:
        current_price: Current price
        supply_proximal: Proximal line of nearest supply above (or None)
        demand_proximal: Proximal line of nearest demand below (or None)
    
    Returns:
        "LOW", "EQ", or "HIGH"
    """
    # Create mock zones if we have proximal values
    supply_zone = None
    demand_zone = None
    
    if supply_proximal is not None:
        supply_zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=supply_proximal,
            distal=supply_proximal + 1,  # Dummy value
            created_at=0,
            base_start_idx=0,
            base_end_idx=0,
            legout_end_idx=0,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
    
    if demand_proximal is not None:
        demand_zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=demand_proximal,
            distal=demand_proximal - 1,  # Dummy value
            created_at=0,
            base_start_idx=0,
            base_end_idx=0,
            legout_end_idx=0,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
    
    # Use existing curve_location function
    loc = curve_location(current_price, supply_zone, demand_zone)
    
    # Convert enum to string
    if loc == CurveLocation.LOW:
        return "LOW"
    elif loc == CurveLocation.HIGH:
        return "HIGH"
    else:
        return "EQ"


def classify_trend(
    pivot_highs: List[int],
    pivot_lows: List[int],
    candles: Any,
    pivots_to_consider: int = 4
) -> str:
    """Classify trend as "UP", "DOWN", or "SIDEWAYS"
    
    Wrapper that analyzes pivot sequences directly.
    
    Args:
        pivot_highs: List of indices where pivot highs occurred
        pivot_lows: List of indices where pivot lows occurred
        candles: OHLC candle data
        pivots_to_consider: Number of recent pivots to analyze
    
    Returns:
        "UP", "DOWN", or "SIDEWAYS"
    """
    # Need at least 2 pivots of each type to determine trend
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "SIDEWAYS"
    
    # Get the most recent pivots
    recent_highs = pivot_highs[-pivots_to_consider:]
    recent_lows = pivot_lows[-pivots_to_consider:]
    
    # Need at least 2 pivots to compare
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return "SIDEWAYS"
    
    # Analyze highs: are they making higher highs (HH)?
    highs_ascending = True
    for i in range(1, len(recent_highs)):
        prev_idx = recent_highs[i - 1]
        curr_idx = recent_highs[i]
        if candles[curr_idx]['high'] <= candles[prev_idx]['high']:
            highs_ascending = False
            break
    
    # Analyze highs: are they making lower highs (LH)?
    highs_descending = True
    for i in range(1, len(recent_highs)):
        prev_idx = recent_highs[i - 1]
        curr_idx = recent_highs[i]
        if candles[curr_idx]['high'] >= candles[prev_idx]['high']:
            highs_descending = False
            break
    
    # Analyze lows: are they making higher lows (HL)?
    lows_ascending = True
    for i in range(1, len(recent_lows)):
        prev_idx = recent_lows[i - 1]
        curr_idx = recent_lows[i]
        if candles[curr_idx]['low'] <= candles[prev_idx]['low']:
            lows_ascending = False
            break
    
    # Analyze lows: are they making lower lows (LL)?
    lows_descending = True
    for i in range(1, len(recent_lows)):
        prev_idx = recent_lows[i - 1]
        curr_idx = recent_lows[i]
        if candles[curr_idx]['low'] >= candles[prev_idx]['low']:
            lows_descending = False
            break
    
    # Classify trend
    # Uptrend: HH and HL
    if highs_ascending and lows_ascending:
        return "UP"
    # Downtrend: LH and LL
    elif highs_descending and lows_descending:
        return "DOWN"
    # Sideways: Mixed signals
    else:
        return "SIDEWAYS"


def should_allow_trade(
    zone: Zone,
    curve_state: str,
    trend_state: str,
    base_score: float,
    parameters: SupplyDemandParameters
) -> Tuple[bool, float]:
    """Determine if a trade should be allowed based on curve + trend gating
    
    Implements the multi-timeframe gating logic:
    - LOW curve: favor demand LONGs, restrict supply SHORTs
    - HIGH curve: favor supply SHORTs, restrict demand LONGs
    - EQ curve: require trend alignment and higher score threshold
    
    Args:
        zone: Zone to evaluate
        curve_state: "LOW", "EQ", or "HIGH"
        trend_state: "UP", "DOWN", or "SIDEWAYS"
        base_score: Base odds enhancer score before EQ bonus
        parameters: Strategy parameters
    
    Returns:
        Tuple of (allow_trade: bool, final_score: float)
    """
    is_long = zone.zone_type == ZoneType.DEMAND
    is_short = zone.zone_type == ZoneType.SUPPLY
    
    final_score = base_score
    
    # Rule 1: LOW curve - allow demand LONGs, restrict supply SHORTs
    if curve_state == "LOW":
        if is_short:
            return False, final_score  # Block supply SHORTs in LOW curve
        # Allow demand LONGs in LOW curve
        return True, final_score
    
    # Rule 2: HIGH curve - allow supply SHORTs, restrict demand LONGs
    elif curve_state == "HIGH":
        if is_long:
            return False, final_score  # Block demand LONGs in HIGH curve
        # Allow supply SHORTs in HIGH curve
        return True, final_score
    
    # Rule 3: EQ curve - require trend alignment and higher threshold
    elif curve_state == "EQ":
        # Check if EQ trades are allowed at all
        if not parameters.allow_eq_trades:
            return False, final_score
        
        # Check trend alignment if required
        if parameters.eq_requires_trend_alignment:
            # LONG trades require UP trend
            if is_long and trend_state != "UP":
                return False, final_score
            # SHORT trades require DOWN trend
            if is_short and trend_state != "DOWN":
                return False, final_score
        
        # Apply EQ score bonus requirement
        final_score = base_score + parameters.eq_min_setup_score_bonus
        
        return True, final_score
    
    # Default: allow trade
    return True, final_score


# ============================================================================
# Odds Enhancer Scoring
# ============================================================================

def odds_enhancer_score(
    zone: Zone,
    current_price: float,
    curve_loc: CurveLocation,
    trend_dir: TrendDirection,
    parameters: SupplyDemandParameters,
    opposing_zone: Optional[Zone] = None
) -> float:
    """Calculate total odds enhancer score for a zone setup
    
    Combines multiple quality factors into a single score:
    - Freshness (0-3 points)
    - Leg-out strength (0-2 points)
    - Time in base (0-2 points)
    - Profit zone available (0-3 points)
    
    Args:
        zone: Zone to score
        current_price: Current price
        curve_loc: Current curve location (HTF)
        trend_dir: Current trend direction (ITF)
        parameters: Strategy parameters
        opposing_zone: Nearest opposing zone (for profit zone calculation)
    
    Returns:
        Total score (typically 0-10+ range)
    """
    total_score = 0.0
    
    # 1. Freshness score (0 / 1.5 / 3 points)
    if zone.freshness_touches == parameters.freshness_touches_best:
        total_score += 3.0  # Fresh (never touched)
    elif zone.freshness_touches == parameters.freshness_touches_good:
        total_score += 1.5  # Good (touched once)
    else:
        total_score += 0.0  # Poor (touched 2+ times)
    
    # 2. Time in base score (0 / 1 / 2 points)
    if zone.base_len <= parameters.base_time_best:
        total_score += 2.0  # Best (≤3 candles)
    elif zone.base_len <= parameters.base_time_good:
        total_score += 1.0  # Good (4-6 candles)
    else:
        total_score += 0.0  # Poor (>6 candles)
    
    # 3. Leg-out strength score (0 / 1 / 2 points)
    # Based on percentage return of the leg-out move
    if zone.legout_return >= parameters.legout_strength_high_threshold:
        total_score += 2.0  # Strong (≥10%)
    elif zone.legout_return >= parameters.legout_strength_mid_threshold:
        total_score += 1.0  # Moderate (≥5%)
    else:
        total_score += 0.0  # Weak (<5%)
    
    # 4. Profit zone score (0 / 1.5 / 3 points)
    # Based on available R multiple to opposing zone
    if opposing_zone is not None:
        # Calculate entry and stop for this zone
        entry_price = zone.proximal
        
        # Calculate stop with buffer
        if zone.zone_type == ZoneType.DEMAND:
            # Long position: stop below distal
            stop_loss = zone.distal * (1 - parameters.stop_buffer_pct)
        else:
            # Short position: stop above distal
            stop_loss = zone.distal * (1 + parameters.stop_buffer_pct)
        
        risk = abs(entry_price - stop_loss)
        
        if risk > 0:
            # Calculate max reward to opposing zone proximal
            if zone.zone_type == ZoneType.DEMAND:
                # Long: opposing zone is supply above
                max_reward = abs(opposing_zone.proximal - entry_price)
            else:
                # Short: opposing zone is demand below
                max_reward = abs(entry_price - opposing_zone.proximal)
            
            available_r = max_reward / risk
            
            if available_r >= 3.0:
                total_score += 3.0  # Excellent (≥3R available)
            elif available_r >= 2.0:
                total_score += 1.5  # Good (≥2R available)
            else:
                total_score += 0.0  # Poor (<2R available)
    
    return total_score


# ============================================================================
# Execution-Specific Functions
# ============================================================================

def check_intrabar_exit(
    trade_plan: TradePlan,
    candle: Dict[str, Any],
    parameters: SupplyDemandParameters,
    stop_wins_on_same_bar: bool = True
) -> Optional[str]:
    """Check if position should exit on current candle (stop or target hit)
    
    Evaluates intrabar price action to determine if stop loss or take profit
    target was hit during the candle.
    
    Args:
        trade_plan: Active trade plan with filled order
        candle: Current OHLC candle
        parameters: Strategy parameters (not currently used but kept for consistency)
        stop_wins_on_same_bar: If both stop and target hit on same bar, assume stop wins first
    
    Returns:
        Exit reason string: "STOP", "TARGET", or None if no exit
    
    Logic:
        - Long position:
          - Stop hit if candle low <= stop_loss
          - Target hit if candle high >= take_profit
        - Short position:
          - Stop hit if candle high >= stop_loss
          - Target hit if candle low <= take_profit
        - If both hit on same bar: stop_wins_on_same_bar determines outcome (default: "STOP")
    """
    if trade_plan.order_state != OrderState.FILLED:
        return None
    
    is_long = trade_plan.zone.zone_type == ZoneType.DEMAND
    
    stop_hit = False
    target_hit = False
    
    if is_long:
        # Long position
        stop_hit = candle['low'] <= trade_plan.stop_loss
        target_hit = candle['high'] >= trade_plan.take_profit
    else:
        # Short position
        stop_hit = candle['high'] >= trade_plan.stop_loss
        target_hit = candle['low'] <= trade_plan.take_profit
    
    # Handle both hit on same bar
    if stop_hit and target_hit:
        # Conservative approach: assume stop hit first
        return "STOP" if stop_wins_on_same_bar else "TARGET"
    
    if stop_hit:
        return "STOP"
    
    if target_hit:
        return "TARGET"
    
    return None


def manage_trade_plan(
    trade_plan: TradePlan,
    current_price: float,
    parameters: SupplyDemandParameters
) -> Dict[str, Any]:
    """Manage active trade: update stops based on profit levels
    
    Implements Plan #1 (default):
    - At 2R: Move stop to breakeven
    - At 3R: Keep monitoring (exit handled by check_intrabar_exit)
    
    Note: This function handles stop management only. Exit detection
    should use check_intrabar_exit() which checks intrabar stop/target hits.
    
    Args:
        trade_plan: Active trade plan
        current_price: Current price (typically close of current candle)
        parameters: Strategy parameters
    
    Returns:
        Dictionary with management actions:
        - "update_stop": New stop price if should be moved
        - "current_r": Current R multiple achieved
    """
    # Determine if long or short
    is_long = trade_plan.zone.zone_type == ZoneType.DEMAND
    
    # Calculate current R multiple based on close price
    current_r = calculate_r_multiple(
        trade_plan.actual_entry_price or trade_plan.entry_price,
        current_price,
        trade_plan.stop_loss,
        is_long
    )
    
    result = {
        "update_stop": None,
        "current_r": current_r
    }
    
    # Check if we should move stop to breakeven
    if current_r >= parameters.breakeven_at_r:
        # Move stop to breakeven (entry price) if not already moved
        entry_price = trade_plan.actual_entry_price or trade_plan.entry_price
        if trade_plan.stop_loss != entry_price:
            result["update_stop"] = entry_price
    
    return result


# ============================================================================
# Helper Functions
# ============================================================================

def calculate_trading_costs(
    price: float,
    position_size: float,
    fees_bps: float,
    slippage_bps: float
) -> float:
    """Calculate total trading costs (fees + slippage)
    
    Args:
        price: Trade price
        position_size: Position size in units
        fees_bps: Trading fees in basis points
        slippage_bps: Slippage in basis points
    
    Returns:
        Total cost in dollars
    
    Formula:
        total_bps = fees_bps + slippage_bps
        cost = (price * position_size * total_bps) / 10000
    """
    total_bps = fees_bps + slippage_bps
    cost = (price * position_size * total_bps) / 10000.0
    return cost


def check_limit_order_fill(
    trade_plan: TradePlan,
    candles: Any,
    current_idx: int,
    parameters: SupplyDemandParameters
) -> bool:
    """Check if a limit order should be filled based on price action
    
    Args:
        trade_plan: Trade plan with pending limit order
        candles: OHLC candle data
        current_idx: Current candle index
        parameters: Strategy parameters
    
    Returns:
        True if order should be filled, False otherwise
    
    Side effects:
        Updates trade_plan.order_state, trade_plan.filled_at_idx,
        trade_plan.actual_entry_price, and trade_plan.entry_cost
    
    Rules:
        - Long (DEMAND): fills if candle's low <= limit price
        - Short (SUPPLY): fills if candle's high >= limit price
        - TTL: Cancel if (current_idx - placed_at_idx) >= ttl_bars
    """
    # Check if order is still pending
    if trade_plan.order_state != OrderState.PENDING:
        return False
    
    # Check TTL expiration
    if parameters.ttl_bars is not None and trade_plan.placed_at_idx is not None:
        bars_elapsed = current_idx - trade_plan.placed_at_idx
        if bars_elapsed >= parameters.ttl_bars:
            # Cancel the order
            trade_plan.order_state = OrderState.CANCELLED
            return False
    
    # Get current candle
    candle = candles[current_idx]
    limit_price = trade_plan.entry_price
    
    # Check if price touched the limit
    is_long = trade_plan.zone.zone_type == ZoneType.DEMAND
    touched = False
    
    if is_long:
        # Long: fills if low <= limit
        touched = candle['low'] <= limit_price
    else:
        # Short: fills if high >= limit
        touched = candle['high'] >= limit_price
    
    if touched:
        # Order is filled
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = current_idx
        
        # Calculate actual entry price with slippage
        # Slippage works against us: longs pay more, shorts receive less
        slippage_amount = (limit_price * parameters.slippage_bps) / 10000.0
        
        if is_long:
            actual_price = limit_price + slippage_amount
        else:
            actual_price = limit_price - slippage_amount
        
        trade_plan.actual_entry_price = actual_price
        
        # Calculate entry costs (fees + slippage)
        trade_plan.entry_cost = calculate_trading_costs(
            actual_price,
            trade_plan.position_size,
            parameters.fees_bps,
            parameters.slippage_bps
        )
        
        return True
    
    return False


def calculate_pnl_with_costs(
    trade_plan: TradePlan,
    exit_price: float,
    parameters: SupplyDemandParameters
) -> float:
    """Calculate profit/loss including all trading costs
    
    Args:
        trade_plan: Trade plan with filled order
        exit_price: Exit price
        parameters: Strategy parameters
    
    Returns:
        Net profit/loss in dollars
    
    Formula:
        For long: PnL = (exit_price - actual_entry_price) * position_size - entry_cost - exit_cost
        For short: PnL = (actual_entry_price - exit_price) * position_size - entry_cost - exit_cost
    """
    if trade_plan.order_state != OrderState.FILLED or trade_plan.actual_entry_price is None:
        return 0.0
    
    is_long = trade_plan.zone.zone_type == ZoneType.DEMAND
    
    # Calculate exit cost
    exit_cost = calculate_trading_costs(
        exit_price,
        trade_plan.position_size,
        parameters.fees_bps,
        parameters.slippage_bps
    )
    
    # Calculate gross PnL
    if is_long:
        gross_pnl = (exit_price - trade_plan.actual_entry_price) * trade_plan.position_size
    else:
        gross_pnl = (trade_plan.actual_entry_price - exit_price) * trade_plan.position_size
    
    # Subtract costs
    net_pnl = gross_pnl - trade_plan.entry_cost - exit_cost
    
    return net_pnl
