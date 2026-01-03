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

def calculate_r_multiple(


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
