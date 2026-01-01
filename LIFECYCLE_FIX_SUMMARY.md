# Trade Lifecycle and Exit Logic Fix - Summary

## Problem Statement

The backtest was not properly simulating trade lifecycle:
1. **Filled trades had exit_idx == entry_idx** (positions not simulated across bars)
2. **Exit reasons were dict-like text** instead of clean string enums
3. **No intrabar exit checks** - stops and targets never hit
4. **Integrity validation issues** - false flagging trades due to incorrect field checks

## Solution Implemented

### 1. Intrabar Exit Detection (`check_intrabar_exit`)

Added new function in `strategy.py` that checks if stop or target was hit using candle high/low:

```python
def check_intrabar_exit(
    trade_plan: TradePlan,
    candle: Dict[str, Any],
    parameters: SupplyDemandParameters,
    stop_wins_on_same_bar: bool = True
) -> Optional[str]:
    """Check if position should exit on current candle"""
    # Long: stop hit if low <= stop, target hit if high >= target
    # Short: stop hit if high >= stop, target hit if low <= target
    # Conservative: if both hit, STOP wins by default
```

**Key Design Decisions:**
- Uses intrabar high/low (not just close price)
- Returns simple string: "STOP", "TARGET", or None
- Conservative same-bar rule: STOP wins if both hit
- Configurable via `stop_wins_on_same_bar` parameter

### 2. Updated Trade Management (`manage_trade_plan`)

Separated concerns - now only handles stop management:

```python
def manage_trade_plan(
    trade_plan: TradePlan,
    current_price: float,
    parameters: SupplyDemandParameters
) -> Dict[str, Any]:
    """Manage active trade: update stops based on profit levels"""
    # Only handles breakeven moves at 2R
    # Exit detection is now separate (check_intrabar_exit)
```

**Changes:**
- No longer returns "take_profit" boolean
- Only returns "update_stop" if breakeven move triggered
- Exit detection delegated to `check_intrabar_exit`

### 3. Runner Position Tracking

Updated `execute_backtest_for_symbol` in `runner.py`:

**Before:**
```python
active_plans = []  # Mixed pending and filled orders
# Exit logic didn't actually check stop/target hits
```

**After:**
```python
pending_plans = []    # Limit orders not yet filled
open_positions = []   # Filled orders (active positions)

# Proper lifecycle:
# 1. Check fills on pending orders
# 2. Check exits on open positions (intrabar)
# 3. Apply stop management
# 4. EOD close any remaining positions
```

**Key Improvements:**
- Positions tracked across multiple bars
- Exit detection on every bar using `check_intrabar_exit`
- Stop management updates applied but don't exit position
- EOD_CLOSE applied to remaining open positions

### 4. Exit Reason Normalization

**Before:**
```python
exit_reason = manage_trade_plan(...)  # Returned dict
# Stored as dict-like string in CSV
```

**After:**
```python
exit_reason = check_intrabar_exit(...)  # Returns "STOP" or "TARGET"
# Clean string stored in CSV
```

**Valid Exit Reasons:**
- `"STOP"` - Stop loss hit
- `"TARGET"` - Take profit hit
- `"EOD_CLOSE"` - Position still open at end of data
- `"TTL_CANCEL"` - Order expired (not a fill, no trade record)

### 5. Integrity Validation Fix

Updated `runner.py` to include both field names:

```python
trades.append({
    'planned_R': plan.r_multiple,
    'planned_r': plan.r_multiple,  # Added for integrity validation
    # ... other fields
})
```

The `integrity.py` already had fallback logic:
```python
planned_r = trade.get('planned_r')
if planned_r is None:
    planned_r = trade.get('r_multiple')
```

## Verification Results

### Manual Tests (verify_lifecycle.py)
All unit tests pass:
- ✅ Long stop hit detection
- ✅ Long target hit detection
- ✅ No exit (position stays open)
- ✅ Both hit (STOP wins)

### Experiment Run
```
Command: python3 scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

Results:
- Total Trades:    25
- Filled Trades:   25
- Win Rate:        40.00%
- Violations:      0 (CLEAN)
```

### Artifact Validation

**trades.csv sample:**
```csv
entry_idx  exit_idx  exit_reason  holding_period
129        130       STOP         1 bar
232        249       STOP         17 bars  ✓
335        360       TARGET       25 bars  ✓
417        422       STOP         5 bars   ✓
```

**violations.json:**
```json
{
  "total_trades": 25,
  "clean": true,
  "violation_counts": {},
  "violations": []
}
```

**Key Metrics:**
- ✅ `exit_idx > entry_idx` in most trades (realistic holding periods)
- ✅ Exit reasons are clean strings ("STOP", "TARGET")
- ✅ No integrity violations (planned_R validation working)
- ✅ Both `planned_R` and `planned_r` fields present in CSV

### Edge Cases Handled

1. **Same-bar entry and exit**: Valid if target immediately hit
   - Example: entry_idx=993, exit_idx=993, exit_reason="TARGET"
   - This means limit order filled AND target hit on same candle

2. **TTL cancellation**: Doesn't create trade record (order never filled)

3. **EOD close**: Any remaining open positions closed at last candle with "EOD_CLOSE"

4. **Stop updates**: Breakeven moves persist across bars (not reset)

## Testing

### New Test File
`tests/test_supply_demand_lifecycle.py` with comprehensive coverage:

**TestIntrabarExitDetection:**
- Long stop hit
- Long target hit
- Long no exit
- Short stop hit
- Short target hit
- Both hit (stop wins)
- Both hit (target wins when configured)

**TestLifecycleSimulation:**
- Position held multiple bars before target
- Stop hit on later bar
- EOD close for open positions

### Existing Tests
- No breaking changes to existing tests
- `test_runner.py` still passes (only checks column existence)

## Documentation Updates

Updated `strategies/supply_demand_v1/README.md`:

**Added sections:**
1. Exit Detection and Lifecycle
2. Exit Reasons table
3. Same-Bar Stop and Target Rule
4. Updated Trade Management pseudocode
5. Updated trades.csv schema

**Key Points Documented:**
- Intrabar high/low used for exit detection
- Conservative same-bar rule (STOP wins)
- Separation of exit detection and stop management
- Position lifecycle: fill → hold → exit

## Files Changed

1. **strategies/supply_demand_v1/strategy.py**
   - Added `check_intrabar_exit()` function
   - Updated `manage_trade_plan()` to only handle stops

2. **strategies/supply_demand_v1/runner.py**
   - Split pending/open position tracking
   - Added intrabar exit checking
   - Normalized exit reasons
   - Added EOD close logic
   - Added both 'planned_R' and 'planned_r' fields

3. **strategies/supply_demand_v1/README.md**
   - Documented exit detection rules
   - Updated pseudocode
   - Updated artifact schema

4. **tests/test_supply_demand_lifecycle.py** (NEW)
   - Comprehensive lifecycle tests

5. **verify_lifecycle.py** (NEW, temporary)
   - Manual verification script

## Acceptance Criteria Met

✅ **Filled trades have exit_idx > entry_idx** (except immediate exits)
✅ **Some trades hit TARGET** (realistic data shows both STOP and TARGET)
✅ **violations.json no longer false flags** (0 violations on test run)
✅ **All tests pass** (manual verification + lifecycle tests)
✅ **CLI run produces artifacts** (summary.json, trades.csv, violations.json, zones.csv, run_manifest.json)
✅ **Exit reasons normalized** ("STOP", "TARGET", "EOD_CLOSE")
✅ **Deterministic same-bar rule** (STOP wins by default, documented and tested)
✅ **Integrity checks work** (planned_R field correctly validated)

## Next Steps

This PR is ready for review. The implementation:
- Makes minimal changes to fix the core issues
- Maintains backward compatibility with artifact schema
- Adds comprehensive test coverage
- Documents all behavior changes
- Passes all validation checks
