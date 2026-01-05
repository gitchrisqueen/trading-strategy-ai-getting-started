# RTF Entry Refinement Implementation Summary

## Overview

This PR adds a **Refinement Timeframe (RTF) entry confirmation stage** to the Supply & Demand V1 trading strategy. The RTF stage acts as a filter that runs AFTER the proximity trigger passes and BEFORE orders are placed.

## What Was Implemented

### 1. RTF Refinement Functions (strategy_core.py)

Added six refinement pattern detection functions:

- **`check_bullish_engulfing()`** - Detects bullish engulfing pattern (bearish candle followed by bullish candle that engulfs it)
- **`check_bearish_engulfing()`** - Detects bearish engulfing pattern (bullish candle followed by bearish candle that engulfs it)
- **`check_bullish_rejection()`** - Detects bullish rejection wick (price drops into zone but closes in upper half with significant lower wick)
- **`check_bearish_rejection()`** - Detects bearish rejection wick (price rises into zone but closes in lower half with significant upper wick)
- **`check_bullish_micro_break()`** - Detects bullish structure break (current close > previous high)
- **`check_bearish_micro_break()`** - Detects bearish structure break (current close < previous low)

Plus the main refinement function:

- **`check_rtf_refinement()`** - Main function that selects and applies the appropriate refinement rule based on configuration and polarity

### 2. Configuration Parameters

Added three new parameters to `SupplyDemandParameters`:

```python
rtf_refinement_enabled: bool = False  # Enable/disable refinement (default: disabled)
rtf_refinement_rule: str = "engulfing"  # Rule to use: "engulfing", "rejection", or "micro_break"
rtf_refinement_lookback: int = 2  # Number of candles for refinement context
```

### 3. Integration in Backtest Loop (csv_backtest_adapter.py)

The RTF refinement check is inserted at line ~1650 in the backtest loop:

**Flow:**
1. Zone passes curve gating ✓
2. Zone passes trend gating ✓
3. Zone passes scoring threshold ✓
4. Zone passes proximity trigger ✓
5. **→ RTF refinement check (NEW)** ← Inserted here
6. Build trade plan ✓
7. Place order ✓

**Behavior:**
- If refinement **passes**: Continue to order placement
- If refinement **fails**: Skip order, keep zone active, allow future attempts

### 4. Decision Funnel Metrics

Added three new metrics to track refinement effectiveness:

```json
{
  "refinement_attempts": 0,  // Number of times refinement was attempted
  "refinement_pass": 0,      // Number of times refinement passed
  "refinement_fail": 0       // Number of times refinement failed
}
```

These metrics appear in:
- `decision_funnel.json` artifact
- Console output (aggregate section)

### 5. Tests

Created comprehensive test suite in `tests/test_supply_demand_rtf_refinement.py`:

- Tests for each individual refinement function
- Tests for direction-aware logic (LONG vs SHORT)
- Tests for disabled/enabled states
- Tests for edge cases (insufficient candles, unknown rules)

Total: **22 test cases** covering all refinement patterns and edge cases

## Key Design Decisions

### 1. Disabled by Default

RTF refinement is **disabled by default** to preserve backward compatibility:

```yaml
rtf_refinement:
  enabled: false  # Must explicitly enable
```

### 2. Direction-Aware Logic

Refinement logic adapts based on **current polarity** (time-relative), not original zone type:

- **LONG (DEMAND polarity)**: Uses bullish refinement patterns
- **SHORT (SUPPLY polarity)**: Uses bearish refinement patterns

This is critical for polarity flipping zones.

### 3. Candle-Local Performance

All refinement checks use **O(1) time complexity**:
- Access only `current_idx` and `current_idx - lookback` candles
- No loops over all candles or all zones
- Fast enough for intra-bar execution

### 4. Non-Destructive Failure

When refinement fails:
- Order is NOT placed
- Zone remains ACTIVE in manager
- Future candles can attempt refinement again

This allows zones to wait for better entry signals without being permanently rejected.

### 5. Three Rule Options

Provides flexibility for different market conditions:

- **engulfing**: Best for reversal confirmation
- **rejection**: Best for bounce plays off zone boundaries
- **micro_break**: Best for momentum confirmation

## How to Use

### 1. Enable in Experiment Config

```yaml
# experiments/your_config.yaml
rtf_refinement:
  enabled: true
  rule: "engulfing"  # or "rejection" or "micro_break"
  lookback: 2
```

### 2. Run Experiment

```bash
python scripts/run_supply_demand_v1.py --config experiments/your_config.yaml
```

### 3. Check Results

View refinement metrics in console output:

```
DECISION FUNNEL (Aggregate)
================================================================================
...
  ├─ Rejected (Proximity):   50
  ├─ Refinement Attempts:    40
  │  ├─ Passed:              15
  │  └─ Failed:              25
Orders Placed:               15
```

Or in `decision_funnel.json`:

```json
{
  "aggregate": {
    "refinement_attempts": 40,
    "refinement_pass": 15,
    "refinement_fail": 25
  }
}
```

## Expected Impact

With RTF refinement enabled, you should observe:

1. **Fewer orders placed** - Refinement filters out lower-quality entries
2. **Orders placed later** - After proximity + refinement confirmation
3. **Higher fill ratio** - Orders placed at better entry points
4. **Better R-multiples** - Improved entry timing leads to better risk/reward

## Validation

### Backward Compatibility

✅ **With refinement disabled** (default):
- Behaves identically to previous version
- Zero impact on existing experiments
- All metrics unchanged

### With Refinement Enabled

✅ **Runs successfully** with all three rules (engulfing, rejection, micro_break)
✅ **Metrics tracked** in decision_funnel.json
✅ **Deterministic** - Same config produces same artifacts

## Files Modified

- `strategies/supply_demand_v1/strategy_core.py` (+380 lines)
- `strategies/supply_demand_v1/strategy.py` (+4 lines)
- `strategies/supply_demand_v1/csv_backtest_adapter.py` (+27 lines)
- `experiments/sd_v1_default.yaml` (+7 lines)
- `experiments/sd_v1_rtf_test.yaml` (new file)
- `tests/test_supply_demand_rtf_refinement.py` (new file, +489 lines)

## Future Enhancements

Possible future improvements:

1. **Multiple rules** - Allow combining multiple refinement rules (e.g., engulfing AND rejection)
2. **Adaptive thresholds** - Adjust wick ratios, lookback dynamically based on volatility
3. **RTF timeframe** - Use actual 5m candles for refinement instead of LTF candles
4. **Machine learning** - Train model to predict optimal refinement rule per zone
5. **Volume confirmation** - Add volume-based refinement rules

## References

- **TradingStrategySpec.md Section 5.1** - Original mention of RTF in multi-timeframe framework
- **Problem Statement** - Original requirements for this PR
- **Tests** - `tests/test_supply_demand_rtf_refinement.py` for usage examples
