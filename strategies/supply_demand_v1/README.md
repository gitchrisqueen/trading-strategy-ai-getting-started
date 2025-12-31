# Supply and Demand Trading Strategy v1

## Strategy Summary

This strategy implements a Supply and Demand (S&D) zone-based trading approach for cryptocurrency markets. The core concept revolves around identifying institutional supply/demand zones through price action patterns and trading retracements into these zones.

### Key Concepts

- **Supply Zones**: Price areas where selling pressure historically overwhelms buying pressure (Rally-Base-Drop pattern)
- **Demand Zones**: Price areas where buying pressure historically overwhelms selling pressure (Drop-Base-Rally pattern)
- **Multi-timeframe Analysis**: Uses HTF (Higher Time Frame), ITF (Intermediate Time Frame), and LTF (Lower Time Frame) to align entries with broader market structure

### Strategy Logic

1. **Zone Detection**: Identify supply/demand zones using "boring" (consolidation) and "exciting" (momentum) candle patterns
2. **Curve Analysis (HTF)**: Determine if price is high, low, or in equilibrium within the broader range
3. **Trend Analysis (ITF)**: Identify directional bias (uptrend, downtrend, sideways)
4. **Scoring System**: Apply odds enhancers to rate setup quality based on:
   - Zone freshness (has price returned to the zone?)
   - Leg-out strength (momentum of breakout from zone)
   - Time in base (number of consolidation candles)
   - Available profit zone (distance to opposing zone)
5. **Entry Execution**: Place limit orders at zone proximal lines with stops beyond distal lines
6. **Trade Management**: Move stop to breakeven at 2R, take profit at 3R (minimum)

## Assumptions

- **Market Type**: Cryptocurrency spot or perpetual futures (Binance-style data)
- **Timeframes**:
  - HTF (Higher Time Frame): 4H
  - ITF (Intermediate Time Frame): 1H  
  - LTF (Lower Time Frame): 15m
  - RTF (Refining Time Frame, optional): 5m
- **Risk Management**: Maximum 2% risk per trade
- **Minimum Reward-to-Risk**: 3:1 (3R minimum)
- **Entry Type**: Limit orders at proximal zone boundaries (default)
- **Position Sizing**: Based on 2% risk rule

## Parameters (Configurable)

### Candle Classification
- `boring_body_ratio`: 0.50 (body <= 50% of range = boring candle)
- `exciting_body_ratio`: 0.50 (body > 50% of range = exciting candle)

### Zone Detection
- `min_base_candles`: 1
- `max_base_candles`: 6 (for optimal scoring)
- `min_legout_candles`: 1

### Scoring Thresholds
- `min_setup_score`: 6.0 (minimum total score to take trade)
- `freshness_touches_best`: 0 (fresh zone = 3 points)
- `freshness_touches_good`: 1 (1 touch = 1.5 points)
- `base_time_best`: 3 (≤3 candles = 2 points)
- `base_time_good`: 6 (4-6 candles = 1 point)

### Trade Management
- `risk_pct`: 0.02 (2% of account per trade)
- `breakeven_at_r`: 2.0 (move stop to BE at 2R)
- `take_profit_at_r`: 3.0 (close position at 3R)
- `min_reward_risk`: 3.0 (minimum R:R to consider trade)

### Multi-Timeframe
- `htf_period`: "4H" (curve analysis)
- `itf_period`: "1H" (trend analysis)
- `ltf_period`: "15m" (zone detection and entry)

## How to Run Backtest Notebook

### Prerequisites

1. Ensure you have the trading-strategy environment set up (see main repository README)
2. Install dependencies via Poetry:
   ```bash
   poetry install
   ```

### Running the Backtest

1. Navigate to the notebooks directory
2. Open the supply_demand_v1 backtest notebook (to be created)
3. Execute cells in order:
   - Import dependencies
   - Load parameters from `strategies/supply_demand_v1/strategy.py`
   - Load market data
   - Run backtest with `create_strategy_universe()`, `create_indicators()`, and `decide_trades()`
   - Visualize results

Example workflow:
```python
from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    create_strategy_universe,
    create_indicators,
    decide_trades
)

# Initialize parameters with defaults or custom values
params = SupplyDemandParameters()

# Run backtest using Trading Strategy framework
# (see example notebooks in notebooks/single-backtest/ for complete setup)
```

## How to Run Tests

Currently, this is a skeleton implementation with no business logic or tests. 

Once implemented, tests can be run using:

```bash
# Run all tests
poetry run pytest

# Run specific test file (when created)
poetry run pytest tests/test_supply_demand_v1.py

# Run with verbose output
poetry run pytest -v tests/test_supply_demand_v1.py
```

### Expected Test Coverage (when implemented)

- Candle classification (boring vs exciting)
- Zone detection (DBR and RBD patterns)
- Proximal/distal line calculation
- Zone freshness tracking
- Curve location detection
- Trend identification
- Odds enhancer scoring
- Position sizing calculations
- Trade management logic

## Implementation Status

**Current Version**: v1.0-skeleton

This package currently contains:
- ✅ Complete text-only specification (TradingStrategySpec.md)
- ✅ Documentation and README
- ✅ Strategy module structure with function stubs
- ❌ Business logic implementation (planned for future PR)
- ❌ Backtest notebook (planned for future PR)
- ❌ Unit tests (planned for future PR)

## Future Enhancements (v2+)

- Confirmation entry mode (wait for reversal confirmation)
- Advanced trailing stops (S&D-based trail)
- Partial penetration freshness nuance
- Anticipatory trend analysis
- Asset-class specific odds enhancers
- Additional timeframe combinations
- Risk-per-day/week limits

## References

- Full specification: [TradingStrategySpec.md](./TradingStrategySpec.md)
- Trading Strategy SDK: https://tradingstrategy.ai/docs/
- Example strategies: ../../notebooks/single-backtest/

## License

MIT (inherited from parent repository)
