"""Supply & Demand V1 Upstream Adapter (decide_trades interface)

This module provides an adapter that integrates the Supply & Demand V1 strategy
with the TradingStrategy.ai upstream execution framework.

The adapter implements the standard decide_trades() interface expected by
run_backtest_inline() and provides a bridge between:
- Framework-agnostic strategy logic (strategy_core.py)
- Upstream execution framework (tradeexecutor package)

Key Differences from CSV Adapter:
- Uses PositionManager API for trade execution (no manual fill simulation)
- Leverages framework's position tracking and PnL calculation
- No manual TTL or order deduplication (handled by framework)
- Returns TradeExecution objects instead of custom TradePlan

Usage (requires trade-executor installed):
    from strategies.supply_demand_v1.decide_trades_adapter import decide_trades_sd_v1
    from tradeexecutor.backtest.backtest_runner import run_backtest_inline
    
    result = run_backtest_inline(
        name="Supply & Demand V1",
        decide_trades=decide_trades_sd_v1,
        # ... other params
    )

Installation:
    The trade-executor package must be installed to use this adapter:
    
    # Clone trade-executor to sibling directory
    cd ..
    git clone https://github.com/tradingstrategy-ai/trade-executor
    cd trading-strategy-ai-getting-started
    
    # Install with Poetry (editable mode)
    poetry install
    
    The pyproject.toml already references ../trade-executor as an editable dependency.

Note: This adapter is OPTIONAL. The CSV backtest adapter (csv_backtest_adapter.py)
remains the default path for running experiments and generating artifacts.
"""

# Guard imports - tradeexecutor may not be installed
try:
    from tradeexecutor.strategy.pandas_trader.strategy_input import StrategyInput
    from tradeexecutor.state.trade import TradeExecution
    from tradeexecutor.strategy.pricing_model import PricingModel
    TRADEEXECUTOR_AVAILABLE = True
except ImportError:
    TRADEEXECUTOR_AVAILABLE = False
    StrategyInput = None
    TradeExecution = None
    PricingModel = None

from typing import List, Dict, Optional, Any

# Import framework-agnostic strategy logic
from .strategy_core import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    CurveLocation,
    TrendDirection,
    detect_zones_dbr_rbd,
    is_zone_fresh,
    find_nearest_fresh_zones_htf,
    curve_location,
    trend_direction_itf,
    odds_enhancer_score,
    should_allow_trade,
    build_trade_plan,
)


def _check_tradeexecutor_available():
    """Raise clear error if trade-executor is not installed"""
    if not TRADEEXECUTOR_AVAILABLE:
        raise ImportError(
            "The trade-executor package is not installed or not available.\n\n"
            "To use the upstream adapter (decide_trades_sd_v1), you must install trade-executor:\n\n"
            "1. Clone trade-executor to a sibling directory:\n"
            "   cd ..\n"
            "   git clone https://github.com/tradingstrategy-ai/trade-executor\n"
            "   cd trading-strategy-ai-getting-started\n\n"
            "2. Install dependencies with Poetry:\n"
            "   poetry install\n\n"
            "The pyproject.toml already references ../trade-executor as an editable dependency.\n\n"
            "If you only need to run CSV backtests (experiments), use:\n"
            "   python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml\n\n"
            "The CSV backtest adapter does NOT require trade-executor."
        )


def decide_trades_sd_v1(
    input: "StrategyInput",
) -> List["TradeExecution"]:
    """Supply & Demand V1 strategy - upstream-compatible decide_trades function
    
    This function implements the standard decide_trades() interface expected by
    the TradingStrategy.ai upstream execution framework. It wraps the core S&D
    strategy logic (zone detection, MTF gating, scoring) and expresses trading
    intent using the PositionManager API.
    
    Args:
        input: StrategyInput containing:
            - timestamp: Current decision timestamp
            - strategy_universe: Multi-timeframe candle data
            - state: Portfolio state (positions, cash, etc.)
            - indicators: Pre-calculated indicators (not used by S&D)
            - parameters: Strategy configuration (SupplyDemandParameters)
    
    Returns:
        List of TradeExecution objects representing trade intent (opens/closes)
    
    Trading Logic:
        1. Detect zones on LTF (15m default)
        2. Analyze HTF curve (4h) and ITF trend (1h)
        3. Filter zones by MTF gating rules
        4. Score setups using odds enhancers
        5. Generate trade plans for high-quality setups
        6. Express intent via position_manager.open_spot() / open_short()
    
    Notes:
        - Framework handles order fills, TTL, position tracking, PnL
        - No manual fill simulation needed
        - Supports both LONG (demand zones) and SHORT (supply zones)
        - Respects min_reward_risk and min_setup_score thresholds
    
    Raises:
        ImportError: If trade-executor package is not installed
    """
    _check_tradeexecutor_available()
    
    # Get inputs
    timestamp = input.timestamp
    position_manager = input.get_position_manager()
    state = input.state
    parameters = input.parameters
    strategy_universe = input.strategy_universe
    
    # Convert parameters to SupplyDemandParameters if not already
    if not isinstance(parameters, SupplyDemandParameters):
        # If parameters is a dict-like object, extract relevant fields
        params = SupplyDemandParameters(
            # Candle classification
            boring_body_ratio=getattr(parameters, 'boring_body_ratio', 0.50),
            exciting_body_ratio=getattr(parameters, 'exciting_body_ratio', 0.50),
            
            # Zone detection
            min_base_candles=getattr(parameters, 'min_base_candles', 1),
            max_base_candles=getattr(parameters, 'max_base_candles', 6),
            proximal_mode=getattr(parameters, 'proximal_mode', 'body'),
            
            # Scoring
            min_setup_score=getattr(parameters, 'min_setup_score', 6.0),
            freshness_touches_best=getattr(parameters, 'freshness_touches_best', 0),
            freshness_touches_good=getattr(parameters, 'freshness_touches_good', 1),
            base_time_best=getattr(parameters, 'base_time_best', 3),
            base_time_good=getattr(parameters, 'base_time_good', 6),
            legout_strength_high_threshold=getattr(parameters, 'legout_strength_high_threshold', 0.10),
            legout_strength_mid_threshold=getattr(parameters, 'legout_strength_mid_threshold', 0.05),
            
            # Trade management
            risk_pct=getattr(parameters, 'risk_pct', 0.02),
            min_reward_risk=getattr(parameters, 'min_reward_risk', 3.0),
            breakeven_at_r=getattr(parameters, 'breakeven_at_r', 2.0),
            take_profit_at_r=getattr(parameters, 'take_profit_at_r', 3.0),
            
            # MTF
            htf_tf=getattr(parameters, 'htf_tf', '4h'),
            itf_tf=getattr(parameters, 'itf_tf', '1h'),
            ltf_tf=getattr(parameters, 'ltf_tf', '15m'),
            
            # Gating
            allow_eq_trades=getattr(parameters, 'allow_eq_trades', True),
            eq_requires_trend_alignment=getattr(parameters, 'eq_requires_trend_alignment', True),
            eq_min_setup_score_bonus=getattr(parameters, 'eq_min_setup_score_bonus', 1.0),
            
            # Trend detection
            pivot_len=getattr(parameters, 'pivot_len', 5),
            pivots_to_consider=getattr(parameters, 'pivots_to_consider', 4),
        )
    else:
        params = parameters
    
    # Get multi-timeframe candle data
    # Note: This assumes strategy_universe.data_universe.candles is organized by timeframe
    # Actual structure depends on how the universe is constructed
    # For now, we'll raise NotImplementedError with guidance
    
    raise NotImplementedError(
        "decide_trades_sd_v1() implementation is incomplete.\n\n"
        "TODO: Complete the following steps:\n"
        "1. Extract multi-timeframe candle data from strategy_universe\n"
        "2. Detect zones on LTF using detect_zones_dbr_rbd()\n"
        "3. Analyze HTF curve using curve_location()\n"
        "4. Analyze ITF trend using trend_direction_itf()\n"
        "5. Score zones using odds_enhancer_score()\n"
        "6. Filter zones using should_allow_trade()\n"
        "7. Build trade plans using build_trade_plan()\n"
        "8. Express intent via position_manager.open_spot() / open_short()\n\n"
        "See notebooks/single-backtest/bitcoin-ma.ipynb for reference on using PositionManager.\n\n"
        "For now, use the CSV backtest adapter:\n"
        "   python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml"
    )
    
    # trades = []
    # 
    # # 1. Get candles by timeframe
    # ltf_candles = strategy_universe.data_universe.candles[params.ltf_tf]
    # htf_candles = strategy_universe.data_universe.candles[params.htf_tf]
    # itf_candles = strategy_universe.data_universe.candles[params.itf_tf]
    # 
    # # 2. Detect zones on LTF
    # zones = detect_zones_dbr_rbd(ltf_candles, params)
    # 
    # # 3. Analyze HTF curve
    # nearest_supply, nearest_demand = find_nearest_fresh_zones_htf(
    #     zones, current_price=ltf_candles[-1]['close'], current_idx=len(ltf_candles)-1
    # )
    # curve = curve_location(nearest_supply, nearest_demand, ltf_candles[-1]['close'])
    # 
    # # 4. Analyze ITF trend
    # trend = trend_direction_itf(itf_candles, params.pivot_len, params.pivots_to_consider)
    # 
    # # 5. Filter and score zones
    # allowed_zones = []
    # for zone in zones:
    #     if is_zone_fresh(zone, ltf_candles, len(ltf_candles)-1):
    #         score = odds_enhancer_score(zone, opposing_zone=None, params=params)
    #         zone.score = score
    #         if should_allow_trade(zone, curve, trend, params):
    #             if score >= params.min_setup_score:
    #                 allowed_zones.append(zone)
    # 
    # # 6. Build trade plans and express intent
    # cash = position_manager.get_current_cash()
    # 
    # for zone in allowed_zones:
    #     plan = build_trade_plan(zone, opposing_zone=None, account_size=cash, params=params)
    #     
    #     if plan and plan.planned_r >= params.min_reward_risk:
    #         # Get trading pair (assumes single pair for now)
    #         pair = strategy_universe.get_single_pair()
    #         
    #         # Express intent based on zone type
    #         if zone.zone_type == ZoneType.DEMAND:
    #             # Open long position
    #             trades += position_manager.open_spot(
    #                 pair=pair,
    #                 value=plan.position_size * plan.entry_price,
    #                 stop_loss=plan.stop_loss,
    #                 take_profit=plan.take_profit,
    #             )
    #         else:  # SUPPLY
    #             # Open short position
    #             trades += position_manager.open_short(
    #                 pair=pair,
    #                 value=plan.position_size * plan.entry_price,
    #                 stop_loss=plan.stop_loss,
    #                 take_profit=plan.take_profit,
    #             )
    # 
    # return trades


def create_indicators(
    timestamp,
    parameters,
    strategy_universe,
    execution_context
):
    """Create indicators for Supply & Demand V1 strategy
    
    The S&D strategy does NOT use traditional indicators like moving averages.
    Instead, it uses raw OHLC data for zone detection and MTF analysis.
    
    This function returns an empty IndicatorSet to satisfy the framework interface.
    
    Args:
        timestamp: Current timestamp
        parameters: Strategy parameters
        strategy_universe: Trading universe with candle data
        execution_context: Execution context
    
    Returns:
        Empty IndicatorSet (S&D uses raw OHLC, not indicators)
    """
    _check_tradeexecutor_available()
    
    from tradeexecutor.strategy.pandas_trader.indicator import IndicatorSet
    
    # S&D strategy doesn't use indicators - it works directly with OHLC data
    indicators = IndicatorSet()
    return indicators


# Example of how to use this adapter in a notebook:
"""
from strategies.supply_demand_v1.decide_trades_adapter import decide_trades_sd_v1, create_indicators
from strategies.supply_demand_v1.strategy_core import SupplyDemandParameters
from tradeexecutor.backtest.backtest_runner import run_backtest_inline

# Define parameters
class Parameters(SupplyDemandParameters):
    id = "supply_demand_v1"
    name = "Supply & Demand V1"
    # ... set other parameters

parameters = Parameters()

# Run backtest
result = run_backtest_inline(
    name=parameters.name,
    engine_version="0.5",
    decide_trades=decide_trades_sd_v1,
    create_indicators=create_indicators,
    client=client,
    universe=strategy_universe,
    parameters=parameters,
    strategy_logging=False,
)

# Access results
state = result.state
trades = list(state.portfolio.get_all_trades())
print(f"Total trades: {len(trades)}")
"""
