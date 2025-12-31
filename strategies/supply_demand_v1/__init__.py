"""Supply and Demand Trading Strategy v1

A zone-based trading strategy that identifies institutional supply and demand areas
through price action patterns and trades retracements into these zones.

This package provides the core strategy implementation following the Supply and Demand
methodology documented in TradingStrategySpec.md.

Key components:
- Zone detection (Drop-Base-Rally and Rally-Base-Drop patterns)
- Multi-timeframe analysis (HTF curve, ITF trend, LTF zones)
- Odds enhancer scoring system
- Risk management with 2% rule and 3R minimum targets
"""

from .strategy import (
    # Parameters and configuration
    SupplyDemandParameters,
    
    # Main strategy functions
    create_strategy_universe,
    create_indicators,
    decide_trades,
    
    # Zone detection and classification
    detect_zones_dbr_rbd,
    identify_boring_candles,
    identify_exciting_candles,
    compute_zone_lines_proximal_distal,
    is_zone_fresh,
    
    # Multi-timeframe analysis
    find_nearest_fresh_zones_htf,
    find_nearest_fresh_supply_above,
    find_nearest_fresh_demand_below,
    curve_location,
    classify_curve,
    trend_direction_itf,
    classify_trend,
    detect_pivot_highs_lows,
    
    # Trade planning and scoring
    odds_enhancer_score,
    should_allow_trade,
    build_trade_plan,
    position_size,
    manage_trade_plan,
    calculate_r_multiple,
    
    # Data classes and enums
    Zone,
    ZoneType,
    CurveLocation,
    TrendDirection,
    EntryMode,
    OrderState,
)

__version__ = "1.0.0-skeleton"
__all__ = [
    # Parameters and configuration
    "SupplyDemandParameters",
    
    # Main strategy functions
    "create_strategy_universe",
    "create_indicators",
    "decide_trades",
    
    # Zone detection and classification
    "detect_zones_dbr_rbd",
    "identify_boring_candles",
    "identify_exciting_candles",
    "compute_zone_lines_proximal_distal",
    "is_zone_fresh",
    
    # Multi-timeframe analysis
    "find_nearest_fresh_zones_htf",
    "find_nearest_fresh_supply_above",
    "find_nearest_fresh_demand_below",
    "curve_location",
    "classify_curve",
    "trend_direction_itf",
    "classify_trend",
    "detect_pivot_highs_lows",
    
    # Trade planning and scoring
    "odds_enhancer_score",
    "should_allow_trade",
    "build_trade_plan",
    "position_size",
    "manage_trade_plan",
    "calculate_r_multiple",
    
    # Data classes and enums
    "Zone",
    "ZoneType",
    "CurveLocation",
    "TrendDirection",
    "EntryMode",
    "OrderState",
]
