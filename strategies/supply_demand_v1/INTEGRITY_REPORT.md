# Backtest Integrity Report - Implementation Summary

## Overview

The Backtest Integrity Report validates that backtests for the Supply & Demand V1 strategy maintain quality and avoid common pitfalls that can lead to unrealistic results.

## Validation Checks

### 1. No Look-Ahead Bias
**Purpose**: Ensure zones are not used for trading decisions before they are fully formed.

**Rule**: A zone cannot be used until after the leg-out is complete (at `zone.created_at` index). The trading decision must occur after zone creation.

**Validation**:
- Checks that `decision_idx > zone_created_at_idx`
- Checks that `decision_time > zone_created_time` (if timestamps available)

**Why it matters**: Using a zone before it's complete constitutes look-ahead bias, a critical flaw that makes backtest results unreliable.

### 2. Entry After Zone Creation
**Purpose**: Verify that trade entry occurs after the zone was created.

**Rule**: The actual entry execution must happen after zone creation time.

**Validation**:
- Checks that `entry_idx > zone_created_at_idx`
- Checks that `entry_time > zone_created_time` (if timestamps available)

**Why it matters**: Similar to look-ahead, entering before zone formation is impossible in live trading.

### 3. R Calculation Consistency
**Purpose**: Verify that the risk-to-reward (R) multiple is calculated correctly.

**Rule**: R = abs(target - entry) / abs(entry - stop)

**Validation**:
- Calculates expected R from trade plan values
- Compares to recorded R with configurable tolerance (default 1%)
- Flags mismatches that exceed tolerance

**Why it matters**: Incorrect R calculations can lead to false confidence in strategy profitability.

### 4. Minimum R Enforcement
**Purpose**: Flag trades that don't meet the minimum R requirement.

**Rule**: Planned R at decision time must be >= `min_reward_risk` (default 3.0)

**Validation**:
- Checks `planned_r >= min_r` threshold
- Uses planned R (decision time) not outcome R (actual result)

**Why it matters**: The strategy requires minimum 3R to maintain positive expectancy. Trades below this threshold violate the strategy rules.

## Usage

### In Python Code

```python
from strategies.supply_demand_v1.integrity import (
    run_integrity_checks,
    print_integrity_report,
)

# Prepare trade data with required fields
trades = [
    {
        'symbol': 'BTC/USDT',
        'entry_price': 50000.0,
        'stop_loss': 49000.0,
        'take_profit': 53000.0,
        'r_multiple': 3.0,  # Planned R at decision time
        'planned_r': 3.0,
        'zone_created_at_idx': 10,
        'zone_created_time': datetime(...),
        'decision_idx': 15,
        'decision_time': datetime(...),
        'entry_idx': 20,
        'entry_time': datetime(...),
    },
    # ... more trades
]

# Run all integrity checks
report = run_integrity_checks(
    trades=trades,
    min_r=3.0,
    r_tolerance=0.01
)

# Print formatted report
print_integrity_report(report, verbose=True)
```

### In Notebooks

The `supply_demand_v1_backtest.ipynb` notebook includes integrity validation automatically. After running the backtest, it will display:

```
================================================================================
BACKTEST INTEGRITY REPORT
================================================================================

Total trades analyzed: 25
Status: ✓ CLEAN

--------------------------------------------------------------------------------
Violation Summary:
--------------------------------------------------------------------------------
✓ Look Ahead: 0
✓ Entry Before Zone: 0
✓ R Calculation Mismatch: 0
✓ Insufficient R: 0

================================================================================
```

If violations are found, detailed information about each violation is displayed including:
- Violation type
- Trade symbol and timing
- Specific reason for the violation
- Detailed metadata for debugging

## Required Trade Fields

For full integrity validation, trades should include:

**Essential fields:**
- `entry_price`: Entry price
- `stop_loss`: Stop loss price
- `take_profit`: Take profit target
- `r_multiple`: Planned R at decision time (or use `planned_r`)

**Optional but recommended:**
- `zone_created_at_idx`: Index where zone was created
- `zone_created_time`: Timestamp of zone creation
- `decision_idx`: Index where trading decision was made
- `decision_time`: Timestamp of decision
- `entry_idx`: Index of entry execution
- `entry_time`: Timestamp of entry
- `symbol`: Trading pair symbol
- `zone_type`: 'demand' or 'supply'

If optional fields are not provided, those specific checks will be skipped.

## Interpreting Results

### Clean Report (✓)
All validations passed. The backtest has:
- No look-ahead bias
- Proper timing of entries
- Correct R calculations
- All trades meet minimum R requirement

### Violations Found (✗)
One or more checks failed. Review the detailed violation list to:
1. Identify which trades have issues
2. Understand the specific violation reason
3. Fix the backtest logic or data
4. Re-run validation to confirm fixes

## Testing

Comprehensive unit tests are in `tests/test_supply_demand_integrity.py`:
- 22 test cases covering all validation scenarios
- Tests for both valid and invalid cases
- Integration tests with realistic scenarios
- Intentional look-ahead detection test

Run tests with:
```bash
pytest tests/test_supply_demand_integrity.py -v
```

## Common Issues

### Look-Ahead Violations
**Symptom**: Decision made at or before zone creation index

**Fix**: Ensure `decision_idx = zone.created_at + N` where N >= 1

**Example**:
```python
# Wrong
decision_idx = zone.created_at  # Same index!

# Correct
decision_idx = zone.created_at + 1  # At least 1 candle after
```

### R Calculation Mismatches
**Symptom**: Recorded R doesn't match calculated R

**Fix**: Store planned R separately from outcome R:
```python
# Calculate planned R at decision time
risk = abs(entry - stop)
reward = abs(target - entry)
planned_r = reward / risk

trade = {
    'planned_r': planned_r,  # What we expected
    'outcome_r': actual_r,   # What actually happened
    'r_multiple': planned_r, # Use planned for validation
}
```

### Timestamp Issues
**Symptom**: Timestamps not in chronological order

**Fix**: Ensure candle generation creates monotonically increasing timestamps:
```python
# Use a separate counter for timestamps
timestamp_idx = 0
for i in range(num_candles):
    candle['timestamp'] = base_time + timedelta(hours=timestamp_idx)
    timestamp_idx += 1
```

## Design Philosophy

The integrity validation follows these principles:

1. **Non-invasive**: Runs after backtest completion, doesn't interfere with strategy logic
2. **Comprehensive**: Checks multiple dimensions of backtest quality
3. **Informative**: Provides detailed reasons and metadata for each violation
4. **Flexible**: Tolerates missing optional fields, skips irrelevant checks
5. **Deterministic**: Same input always produces same output
6. **Testable**: All functions have corresponding unit tests

## References

- Implementation: `strategies/supply_demand_v1/integrity.py`
- Tests: `tests/test_supply_demand_integrity.py`
- Notebook example: `notebooks/supply_demand_v1_backtest.ipynb`
- Strategy core: `strategies/supply_demand_v1/strategy.py`
