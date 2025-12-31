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
    SupplyDemandParameters,
    create_strategy_universe,
    create_indicators,
    decide_trades,
)

__version__ = "1.0.0-skeleton"
__all__ = [
    "SupplyDemandParameters",
    "create_strategy_universe",
    "create_indicators",
    "decide_trades",
]
