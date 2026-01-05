# RTF Timeframe Validation Implementation

## Overview

Added validation to ensure RTF (Refining TimeFrame) is always LOWER than LTF (Lower TimeFrame). This prevents misconfiguration where RTF would not provide finer-grained price action for entry refinement.

## Implementation

### Validation Function

Located in `strategies/supply_demand_v1/csv_backtest_adapter.py`:

```python
def validate_timeframe_hierarchy(ltf_tf: str, rtf_tf: Optional[str]) -> None:
    """Validate that RTF is a lower timeframe than LTF
    
    RTF (Refining TimeFrame) must be LOWER (smaller interval) than LTF (Lower TimeFrame).
    This ensures that RTF provides finer-grained price action for entry refinement.
    
    Args:
        ltf_tf: Lower timeframe string (e.g., '15m', '1h')
        rtf_tf: Refining timeframe string (e.g., '5m', '1m') or None
    
    Raises:
        ValueError: If rtf_tf is greater than or equal to ltf_tf
    """
```

### When Validation Runs

The validation is called in `run_backtest_experiment()` immediately after parameters are created:

```python
params = SupplyDemandParameters(...)

# Validate timeframe hierarchy: RTF must be lower than LTF
validate_timeframe_hierarchy(params.ltf_tf, params.rtf_tf)
```

This ensures invalid configurations are caught early, before any backtesting begins.

## Validation Rules

### Valid Configurations ✓

```yaml
# RTF is None (optional)
timeframes:
  ltf: "15m"
  rtf: null

# RTF < LTF
timeframes:
  ltf: "15m"
  rtf: "5m"   # 5m < 15m ✓

timeframes:
  ltf: "1h"
  rtf: "15m"  # 15m < 1h ✓
```

### Invalid Configurations ✗

```yaml
# RTF == LTF
timeframes:
  ltf: "15m"
  rtf: "15m"  # Equal - ERROR

# RTF > LTF
timeframes:
  ltf: "15m"
  rtf: "1h"   # 1h > 15m - ERROR
```

## Error Messages

The validation provides clear, actionable error messages:

### Example 1: RTF == LTF
```
ValueError: Invalid timeframe configuration: RTF ('15m' = 15m) must be 
LOWER than LTF ('15m' = 15m). RTF is used for entry refinement and must 
provide finer-grained price action. Valid RTF options for LTF='15m': 1m, 5m
```

### Example 2: RTF > LTF
```
ValueError: Invalid timeframe configuration: RTF ('1h' = 60m) must be 
LOWER than LTF ('15m' = 15m). RTF is used for entry refinement and must 
provide finer-grained price action. Valid RTF options for LTF='15m': 1m, 5m
```

### Example 3: Invalid Timeframe String
```
ValueError: Invalid RTF timeframe: 'invalid'. 
Must be one of: 12h, 15m, 1d, 1h, 1m, 2h, 30m, 4h, 5m, 6h
```

## Supported Timeframes

The validation recognizes these standard timeframe strings:

- `'1m'` - 1 minute
- `'5m'` - 5 minutes
- `'15m'` - 15 minutes
- `'30m'` - 30 minutes
- `'1h'` - 1 hour
- `'2h'` - 2 hours
- `'4h'` - 4 hours
- `'6h'` - 6 hours
- `'12h'` - 12 hours
- `'1d'` - 1 day

## Testing

### Unit Tests

Location: `tests/test_rtf_validation.py`

**Test Coverage:**
- ✅ RTF=None is valid (RTF is optional)
- ✅ RTF < LTF combinations are valid
- ✅ RTF == LTF raises ValueError
- ✅ RTF > LTF raises ValueError
- ✅ Invalid LTF raises ValueError
- ✅ Invalid RTF raises ValueError
- ✅ Error messages include valid options

**Run Tests:**
```bash
python3 tests/test_rtf_validation.py
```

### Test Configurations

**Valid Config** (`experiments/sd_v1_valid_rtf_test.yaml`):
```yaml
timeframes:
  ltf: "15m"
  rtf: "5m"  # Valid: 5m < 15m
```

**Invalid Config - Equal** (`experiments/sd_v1_invalid_rtf_test.yaml`):
```yaml
timeframes:
  ltf: "15m"
  rtf: "15m"  # Invalid: equal
```

**Invalid Config - Greater** (`experiments/sd_v1_invalid_rtf_higher_test.yaml`):
```yaml
timeframes:
  ltf: "15m"
  rtf: "1h"  # Invalid: 1h > 15m
```

### Testing the Validation

**Valid config (should succeed):**
```bash
python3 scripts/run_supply_demand_v1.py --config experiments/sd_v1_valid_rtf_test.yaml
# Runs successfully
```

**Invalid config (should fail):**
```bash
python3 scripts/run_supply_demand_v1.py --config experiments/sd_v1_invalid_rtf_test.yaml
# Error: RTF ('15m' = 15m) must be LOWER than LTF ('15m' = 15m)
```

## Rationale

### Why RTF Must Be Lower Than LTF

RTF (Refining TimeFrame) is used for **entry refinement** - analyzing finer-grained price action before placing an order. For this to be meaningful:

1. **Finer granularity required**: RTF must show more detailed price movement than LTF
2. **Entry precision**: Lower timeframes reveal micro-structure (e.g., engulfing patterns, rejections)
3. **Signal quality**: Refinement only adds value when examining higher-resolution data

### Example Scenarios

**Correct Usage:**
- LTF = 15m (zone detection)
- RTF = 5m (check for engulfing pattern on 5m chart before entering)
- ✓ 5m shows 3 candles per 15m candle - provides refinement

**Incorrect Usage:**
- LTF = 15m (zone detection)
- RTF = 15m (check for engulfing on same 15m chart)
- ✗ Same resolution - no additional information

- LTF = 15m (zone detection)
- RTF = 1h (check for engulfing on coarser 1h chart)
- ✗ Less resolution - opposite of refinement

## Backward Compatibility

- **RTF=None remains valid** - RTF is optional
- **Existing valid configs work unchanged** - No breaking changes
- **Invalid configs fail immediately** - Clear error prevents confusion
- **All default configs are valid** - Default RTF='5m' with LTF='15m' passes validation

## Performance Impact

**Negligible** - Validation runs once at config load time:
- O(1) dictionary lookups
- Single comparison
- No impact on backtest performance

## Files Changed

1. **strategies/supply_demand_v1/csv_backtest_adapter.py**
   - Added `validate_timeframe_hierarchy()` function
   - Added validation call in `run_backtest_experiment()`

2. **tests/test_rtf_validation.py** (NEW)
   - 7 unit tests covering all validation scenarios

3. **experiments/sd_v1_valid_rtf_test.yaml** (NEW)
   - Example valid configuration

4. **experiments/sd_v1_invalid_rtf_test.yaml** (NEW)
   - Example invalid configuration (RTF == LTF)

5. **experiments/sd_v1_invalid_rtf_higher_test.yaml** (NEW)
   - Example invalid configuration (RTF > LTF)

## Summary

This change adds a single validation function that:
- ✅ Prevents timeframe misconfiguration
- ✅ Provides clear, actionable error messages
- ✅ Suggests valid alternatives
- ✅ Has comprehensive test coverage
- ✅ Is backward compatible
- ✅ Has zero runtime performance impact

The validation ensures RTF serves its intended purpose: providing finer-grained price action for entry refinement.
