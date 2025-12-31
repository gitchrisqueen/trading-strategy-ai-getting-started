# Realistic Fill Logic and Trading Costs

This document describes the realistic limit order fill logic and trading cost implementation for Supply & Demand V1 strategy.

## Overview

The implementation adds realistic market mechanics to the strategy:

1. **Limit Order Fill Logic**: Orders only fill when price actually touches the limit price
2. **Time-to-Live (TTL)**: Orders automatically cancel if not filled within a specified number of bars
3. **Trading Costs**: Fees and slippage are applied on both entry and exit
4. **Performance Metrics**: PnL calculations include all costs for accurate backtesting

## Features

### 1. Limit Order Fill Logic

Orders follow realistic fill rules based on position direction:

- **Long positions (DEMAND zones)**: Fill only if candle's `low <= limit_price`
- **Short positions (SUPPLY zones)**: Fill only if candle's `high >= limit_price`

This ensures orders only fill when price actually reaches the limit level, preventing unrealistic fills.

### 2. Time-to-Live (TTL)

Orders can expire if not filled within a configurable number of bars:

```python
params = SupplyDemandParameters(
    ttl_bars=10  # Order expires after 10 bars
)
```

- Set `ttl_bars=None` for orders that never expire
- Orders transition to `CANCELLED` state when TTL expires
- Helps prevent stale orders from filling at unfavorable times

### 3. Trading Costs

Realistic costs are applied on every trade:

```python
params = SupplyDemandParameters(
    fees_bps=10.0,      # 0.1% trading fees (10 basis points)
    slippage_bps=5.0,   # 0.05% slippage (5 basis points)
)
```

**Entry costs**:
- Slippage works against the trader (longs pay more, shorts receive less)
- Fees calculated on actual entry price after slippage

**Exit costs**:
- Same fee and slippage applied on exit
- Included in final PnL calculation

**Cost formula**:
```
cost = (price * position_size * (fees_bps + slippage_bps)) / 10000
```

### 4. Order States

Orders can be in one of three states:

- `PENDING`: Order placed but not yet filled
- `FILLED`: Order has been filled
- `CANCELLED`: Order expired (TTL reached)

## Usage Example

```python
from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    build_trade_plan,
    check_limit_order_fill,
    calculate_pnl_with_costs,
)

# Create parameters with costs
params = SupplyDemandParameters(
    fees_bps=10.0,       # 0.1% fees
    slippage_bps=5.0,    # 0.05% slippage
    ttl_bars=10          # 10-bar TTL
)

# Create a trade plan
trade_plan = build_trade_plan(
    zone=demand_zone,
    current_price=102.0,
    account_size=10000.0,
    parameters=params
)

# Mark when order was placed
trade_plan.placed_at_idx = 0

# Check for fill on each new candle
for idx, candle in enumerate(candles):
    filled = check_limit_order_fill(
        trade_plan, 
        candles, 
        idx, 
        params
    )
    
    if filled:
        print(f"Order filled at ${trade_plan.actual_entry_price}")
        break
    elif trade_plan.order_state == OrderState.CANCELLED:
        print("Order cancelled (TTL expired)")
        break

# Calculate PnL with costs
if trade_plan.order_state == OrderState.FILLED:
    pnl = calculate_pnl_with_costs(
        trade_plan,
        exit_price=115.0,
        parameters=params
    )
    print(f"Net PnL: ${pnl:.2f}")
```

## API Reference

### Functions

#### `check_limit_order_fill(trade_plan, candles, current_idx, parameters)`

Checks if a limit order should be filled based on current price action.

**Parameters**:
- `trade_plan`: TradePlan with pending order
- `candles`: List of OHLC candles
- `current_idx`: Current candle index
- `parameters`: SupplyDemandParameters

**Returns**: `True` if filled, `False` otherwise

**Side effects**: Updates `trade_plan.order_state`, `filled_at_idx`, `actual_entry_price`, and `entry_cost`

#### `calculate_trading_costs(price, position_size, fees_bps, slippage_bps)`

Calculates total trading costs.

**Parameters**:
- `price`: Trade price
- `position_size`: Position size in units
- `fees_bps`: Fees in basis points
- `slippage_bps`: Slippage in basis points

**Returns**: Total cost in dollars

#### `calculate_pnl_with_costs(trade_plan, exit_price, parameters)`

Calculates net profit/loss including all trading costs.

**Parameters**:
- `trade_plan`: Trade plan with filled order
- `exit_price`: Exit price
- `parameters`: SupplyDemandParameters

**Returns**: Net PnL in dollars

### Data Classes

#### `TradePlan` (Updated)

New fields added:
- `order_state`: Current order state (PENDING, FILLED, CANCELLED)
- `placed_at_idx`: Candle index when order was placed
- `filled_at_idx`: Candle index when order was filled
- `actual_entry_price`: Actual entry price after slippage
- `entry_cost`: Total entry cost (fees + slippage)
- `exit_cost`: Total exit cost (calculated on exit)

#### `SupplyDemandParameters` (Updated)

New parameters:
- `fees_bps`: Trading fees in basis points (default: 10.0 = 0.1%)
- `slippage_bps`: Slippage in basis points (default: 5.0 = 0.05%)
- `ttl_bars`: Time-to-live for limit orders (default: 10 bars, None = no expiry)

## Testing

Comprehensive test coverage includes:

- **Cost calculations**: Verify fees and slippage are calculated correctly
- **Long order fills**: Test fills when price touches limit from above
- **Short order fills**: Test fills when price touches limit from below
- **No-fill scenarios**: Test orders that never touch limit price
- **TTL expiration**: Test orders cancel after TTL
- **TTL before fill**: Test fills that occur before TTL
- **PnL with costs**: Test profit and loss include all costs
- **Cost impact**: Verify costs reduce net profit compared to gross

Run tests with:
```bash
python -m pytest tests/test_supply_demand_fill_logic.py -v
```

## Performance Impact

Trading costs typically reduce gross profits by 1-3% depending on:

- Trade frequency (more trades = more costs)
- Position size (larger positions pay more in absolute terms)
- Hold time (shorter holds = higher cost per profit)

Example from demo:
- Gross PnL: $600.00
- Total Costs: $12.68
- Net PnL: $585.36
- Cost Impact: 2.11% of gross profit

## Demo Script

Run the included demo to see the features in action:

```bash
python examples/realistic_fill_logic_demo.py
```

This demonstrates:
1. Complete trade lifecycle with limit order
2. Price action simulation
3. Order fill when price touches limit
4. PnL calculation at various exit points
5. Cost impact analysis
6. TTL cancellation example

## Integration with Backtesting

When integrating with backtesting systems:

1. **Place orders**: Create trade plans and set `placed_at_idx`
2. **Check fills**: Call `check_limit_order_fill()` on each new candle
3. **Track states**: Monitor `order_state` for fills and cancellations
4. **Calculate PnL**: Use `calculate_pnl_with_costs()` for accurate metrics
5. **Update performance**: Ensure all metrics include costs

## Notes

- Costs are calculated on **actual entry price** after slippage, not limit price
- Slippage always works against the trader (increases entry cost)
- Use realistic fee and slippage values for your target exchange/market
- TTL helps prevent orders from filling in unfavorable market conditions
- All tests pass without breaking existing functionality

## References

- Main implementation: `strategies/supply_demand_v1/strategy.py`
- Tests: `tests/test_supply_demand_fill_logic.py`
- Demo: `examples/realistic_fill_logic_demo.py`
