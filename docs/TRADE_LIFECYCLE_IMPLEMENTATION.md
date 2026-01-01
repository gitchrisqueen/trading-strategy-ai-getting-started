# Trade Lifecycle Implementation Notes

## Overview

This document explains the trade lifecycle implementation in the Supply & Demand V1 strategy backtest engine.

## Position States

A trade progresses through these states:

```
PLAN CREATED → PENDING → FILLED → OPEN → EXITED
```

1. **PLAN CREATED**: Trade plan generated with zone, entry, stop, target
2. **PENDING**: Limit order placed, waiting for fill
3. **FILLED**: Order filled, position now open
4. **OPEN**: Position held across bars, checked for exit each bar
5. **EXITED**: Position closed (STOP/TARGET/EOD_CLOSE)

## Position Tracking

The runner maintains two separate lists:

```python
pending_plans = []    # OrderState.PENDING - waiting for fill
open_positions = []   # OrderState.FILLED - active positions
```

### Why Separate Lists?

- **Clarity**: Makes it obvious which orders need fill checks vs exit checks
- **Performance**: Don't check exits on pending orders
- **Correctness**: Prevents confusion between pending and active state

## Bar-by-Bar Processing

On each bar, the runner processes in this order:

```python
for idx, candle in enumerate(candles):
    # 1. Update zone freshness
    for zone in zones:
        is_zone_fresh(zone, candles, idx)
    
    # 2. Check fills on pending orders
    for plan in pending_plans:
        if check_limit_order_fill(plan, candles, idx, params):
            # Move to open positions
            open_positions.append(plan)
            pending_plans.remove(plan)
    
    # 3. Check exits on open positions
    for plan in open_positions:
        exit_reason = check_intrabar_exit(plan, candle, params)
        if exit_reason:
            # Record exit and remove from open positions
            update_trade_record(plan, exit_reason, idx, candle)
            open_positions.remove(plan)
        else:
            # Apply stop management (breakeven moves)
            management = manage_trade_plan(plan, candle['close'], params)
            if management['update_stop']:
                plan.stop_loss = management['update_stop']
    
    # 4. Check TTL on pending orders
    for plan in list(pending_plans):
        if plan.placed_at_idx + params.ttl_bars <= idx:
            plan.order_state = OrderState.CANCELLED
            pending_plans.remove(plan)
    
    # 5. Look for new setups
    # ... zone scoring and trade plan generation
```

## Exit Detection Logic

### Why Intrabar Detection?

Consider this scenario:

```
Entry: 100 (LONG)
Stop:  95
Target: 115
```

**Without intrabar detection** (using only close):
```
Bar 1: close=102 → No exit (close above stop, below target)
Bar 2: close=104 → No exit
Bar 3: close=93 → STOP (close below stop)
```

**With intrabar detection** (using high/low):
```
Bar 1: low=99, high=103 → No exit (stop not hit, target not hit)
Bar 2: low=96, high=105 → No exit
Bar 3: low=93, high=94 → STOP (low <= stop)
```

**The Critical Difference:**
Bar 3 might have: `low=93, high=130, close=128`

- **Without intrabar**: Exit at STOP (93) because we only checked close against stop
- **With intrabar**: We correctly detect that stop (95) was hit when low touched 93

### Same-Bar Stop and Target

What if both are hit on the same bar?

```
Candle: low=90, high=120
Stop: 95
Target: 115
```

Both conditions are true:
- Stop hit: `low (90) <= stop (95)` ✓
- Target hit: `high (120) >= target (115)` ✓

**We must make a choice. We choose STOP (conservative).**

**Why conservative?**
1. **Risk management**: Better to underestimate wins than overestimate
2. **Market microstructure**: If price dropped to 90 first, it likely hit stop before bouncing to target
3. **Slippage**: In volatile bars, stop execution quality degrades
4. **Overfitting prevention**: Don't assume best-case execution

**Configurable via parameter:**
```python
exit_reason = check_intrabar_exit(
    plan, candle, params, 
    stop_wins_on_same_bar=True  # Default: conservative
)
```

## Stop Management vs Exit Detection

These are **separate concerns**:

### Exit Detection (`check_intrabar_exit`)
- **Purpose**: Determine if position should be closed
- **When**: Called every bar for open positions
- **How**: Checks candle high/low against stop/target
- **Returns**: "STOP", "TARGET", or None

### Stop Management (`manage_trade_plan`)
- **Purpose**: Update stop price based on profit
- **When**: Called every bar for open positions (if no exit)
- **How**: Calculates current R, moves stop to breakeven at 2R
- **Returns**: dict with 'update_stop' and 'current_r'

**Why separate?**
- Exit detection is about price action (intrabar high/low)
- Stop management is about risk management (profit-based rules)
- They operate on different time scales (intrabar vs close-to-close)

Example:
```python
# Check exit first
exit_reason = check_intrabar_exit(plan, candle, params)

if exit_reason:
    # Exit immediately
    close_position(plan, exit_reason)
else:
    # No exit, apply management
    management = manage_trade_plan(plan, candle['close'], params)
    if management['update_stop']:
        plan.stop_loss = management['update_stop']
```

## Trade Record Lifecycle

### Creation (at fill)
```python
trades.append({
    'symbol': symbol,
    'side': 'LONG',
    'entry': plan.actual_entry_price,
    'stop': plan.stop_loss,
    'target': plan.take_profit,
    'planned_R': plan.r_multiple,
    'planned_r': plan.r_multiple,  # For integrity validation
    'realized_R': None,  # Filled on exit
    'entry_idx': idx,
    'exit_idx': None,  # Filled on exit
    'exit_reason': None,  # Filled on exit
    'pnl': 0.0,  # Filled on exit
})
```

### Update (at exit)
```python
for trade in trades:
    if trade['entry_idx'] == plan.filled_at_idx:
        trade['realized_R'] = calculate_realized_r(...)
        trade['exit_idx'] = idx
        trade['exit_reason'] = exit_reason
        trade['pnl'] = calculate_pnl(...)
        break
```

## Common Patterns and Edge Cases

### Pattern 1: Immediate Exit (Same Bar as Fill)
```
entry_idx=100, exit_idx=100, exit_reason="TARGET"
```
**Meaning**: Limit order filled AND target immediately available on same candle
**Valid**: Yes, can happen in volatile markets
**Example**: Entry=100, Target=105, Candle: low=100 (fill), high=110 (target hit)

### Pattern 2: Multi-Bar Hold
```
entry_idx=100, exit_idx=125, exit_reason="STOP"
```
**Meaning**: Position held for 25 bars before stop hit
**Valid**: Yes, this is the expected behavior

### Pattern 3: EOD Close
```
entry_idx=100, exit_idx=999, exit_reason="EOD_CLOSE"
```
**Meaning**: Position still open when backtest ended
**Valid**: Yes, closed at market close price of last candle

### Pattern 4: TTL Cancellation
```
Order placed at idx=100, cancelled at idx=110 (TTL=10 bars)
```
**Trade record created**: No
**Why**: Order never filled, so no position to track

## Integrity Validation

The integrity checker validates:

### 1. Minimum R Enforcement
```python
if trade['planned_r'] < params.min_reward_risk:
    violation = "Insufficient R"
```

### 2. Entry Timing
```python
if trade['entry_idx'] <= trade['zone_created_at']:
    violation = "Look-ahead bias"
```

### 3. R Calculation
```python
expected_r = abs(target - entry) / abs(entry - stop)
if abs(trade['planned_r'] - expected_r) > tolerance:
    violation = "R calculation mismatch"
```

## Performance Considerations

### Why Not Check Every Pending Order Against Every Zone?

The current implementation only creates one trade plan per zone. This prevents:
- Duplicate orders on the same zone
- Order explosion (N pending orders × M zones checks per bar)
- Ambiguity (which order filled first?)

### Zone Already Traded Check
```python
zone_already_traded = any(
    p.zone == zone for p in pending_plans + open_positions
)
if zone_already_traded:
    continue  # Skip this zone
```

This ensures:
- One position per zone maximum
- Clean position tracking
- No conflicting orders

## Testing Strategy

### Unit Tests
- `test_supply_demand_lifecycle.py`
- Tests individual functions in isolation
- Fast, deterministic

### Integration Tests
- `test_runner.py`
- Tests complete backtest with synthetic data
- Validates artifact generation

### Manual Verification
- Run actual experiments
- Inspect artifacts
- Validate exit_idx > entry_idx
- Check exit reason distribution

## Future Enhancements

Potential improvements (out of scope for this PR):

1. **Partial exits**: Scale out at multiple targets
2. **Trailing stops**: Dynamic stop adjustment beyond breakeven
3. **Time-based exits**: Exit after N bars regardless of price
4. **Multiple positions per zone**: Allow re-entry after first exit
5. **Intrabar fill sequence**: Model order of stop/target hits more precisely

## Summary

The key insight: **Proper backtesting requires tracking position state across bars and using intrabar price action for exits.**

This implementation:
- Separates pending orders from open positions
- Checks exits using intrabar high/low (not just close)
- Applies conservative same-bar rules
- Maintains clean position lifecycle
- Generates accurate artifact data

**Result**: Realistic holding periods, proper exit reasons, zero integrity violations.
