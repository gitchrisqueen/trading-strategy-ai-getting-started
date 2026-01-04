# Fix Active Zone Manager Regression - Implementation Summary

## Problem Statement
After a recent optimization PR, orders were no longer being placed because the runner was using `set()` to store Zone objects, which are mutable `@dataclass` instances and not safely hashable. This caused the active zone manager to fail silently, preventing trade execution.

## Root Cause
```python
# BROKEN CODE (line 1037 in runner.py)
active_zones = set()  # Zones that are created and fresh at current index
active_zones.add(zone)  # FAILS: Zone is mutable @dataclass, not safely hashable
```

The Zone dataclass is mutable and cannot be reliably used as a set member. Python may allow this initially but behavior is undefined and can break activation/evaluation logic.

## Solution
Replace the `set()` with a `Dict[str, Zone]` keyed by a stable zone identifier constructed from immutable fields.

### Key Changes

#### 1. Added `make_zone_id()` Helper Function
```python
def make_zone_id(symbol: str, zone: Zone) -> str:
    """Create a stable, unique identifier for a zone
    
    Uses immutable fields:
    - symbol: Trading pair
    - created_at: Index where zone was created
    - zone_type: SUPPLY or DEMAND
    - proximal: Entry reference price
    - distal: Stop reference price
    
    Returns:
        "BTCUSDT_1234_demand_100.5_99.0"
    """
    zone_type_str = zone.zone_type.value if hasattr(zone.zone_type, 'value') else str(zone.zone_type)
    return f"{symbol}_{zone.created_at}_{zone_type_str}_{zone.proximal}_{zone.distal}"
```

#### 2. Updated Zone Storage Structure
```python
# Build ltf_zones_by_creation with (zone_id, zone) tuples
ltf_zones_by_creation = {}
for zone in ltf_zones:
    zone_id = make_zone_id(symbol, zone)
    if zone.created_at not in ltf_zones_by_creation:
        ltf_zones_by_creation[zone.created_at] = []
    ltf_zones_by_creation[zone.created_at].append((zone_id, zone))

# Use Dict instead of set for active zones
active_zones: Dict[str, Zone] = {}
```

#### 3. Safe Activation/Removal Logic
```python
# Activation: Add zones created at current index
if ltf_idx in ltf_zones_by_creation:
    for zone_id, zone in ltf_zones_by_creation[ltf_idx]:
        active_zones[zone_id] = zone
        total_activations += 1

# Removal: Collect keys first, then delete (no mutation while iterating)
zone_ids_to_remove = []
for zone_id, zone in active_zones.items():
    if not is_zone_fresh_at_idx(zone, ltf_idx):
        zone_ids_to_remove.append(zone_id)
for zone_id in zone_ids_to_remove:
    del active_zones[zone_id]
```

#### 4. Updated Iteration Pattern
```python
# OLD (with set): for zone in active_zones:
# NEW (with dict): for zone_id, zone in active_zones.items():
for zone_id, zone in active_zones.items():
    # Check if already traded
    zone_already_traded = any(
        p.zone == zone for p in pending_plans + open_positions
    )
    # ... rest of trade logic
```

#### 5. Added Runtime Sanity Metrics
```python
# Track activation metrics
total_activations = 0
max_active_zones = 0
active_zones_sum = 0
active_zones_samples = 0

# Update during backtest loop
active_zones_sum += len(active_zones)
active_zones_samples += 1
if len(active_zones) > max_active_zones:
    max_active_zones = len(active_zones)

# Print at end of backtest
avg_active_zones = active_zones_sum / active_zones_samples if active_zones_samples > 0 else 0.0
print(f"Total Activations: {total_activations}")
print(f"Max Active Zones: {max_active_zones}")
print(f"Avg Active Zones: {avg_active_zones:.2f}")

# Warning if zones detected but no activations
if len(ltf_zones) > 0 and total_activations == 0:
    print(f"⚠️  WARNING: {len(ltf_zones)} zones detected but ZERO activations!")
```

## Test Coverage

### New Test File: `test_active_zone_manager.py`

#### Test 1: `test_make_zone_id_creates_stable_identifier`
- Validates zone_id format and uniqueness
- Tests determinism (same zone → same ID)
- Tests differentiation (different zones → different IDs)
- **Status:** ✅ PASS

#### Test 2: `test_active_zone_manager_with_synthetic_candles`
- Generates 500 synthetic candles with higher volatility
- Validates zone detection and activation tracking
- Confirms ltf_zones_by_creation has valid keys
- Confirms orders are placed (12 orders, 6 filled)
- **Status:** ✅ PASS

#### Test 3: `test_active_zone_manager_no_dict_mutation_while_iterating`
- Validates safe dict mutation pattern
- Ensures no RuntimeError from dict size change during iteration
- **Status:** ✅ PASS

### Existing Tests

All existing runner tests pass:
- ✅ TestSyntheticDataGeneration (2 tests)
- ✅ TestRunnerExecution (7 tests)
- ✅ TestIntegrityChecks (2 tests)
- ✅ TestSymbolBacktest (1 test)
- ✅ TestMultiSymbolIsolation (3 tests)
- ✅ TestDecisionFunnel (3 tests)

**Total: 18/18 tests passing**

## Validation Results

### Experiment Run: `sd_v1_default.yaml`

**Before Fix:** Orders Placed = 0 (regression)

**After Fix:**
```
Aggregate Results:
- Zones Detected: 466
- Total Activations: 466 (one per zone)
- Candidates Scored: 4487
- Orders Placed: 257 ✅
- Orders Filled: 7 ✅
- Trades Closed: 7 ✅
- Integrity Violations: 0 ✅

Per-Symbol Breakdown:
- BTC/USDT:  100 zones → 100 activations → 144 orders → 2 filled
- ETH/USDT:   94 zones →  94 activations →   0 orders (filtered)
- SOL/USDT:   97 zones →  97 activations →  12 orders → 2 filled
- MATIC/USDT: 80 zones →  80 activations →  29 orders → 2 filled
- AVAX/USDT:  95 zones →  95 activations →  72 orders → 1 filled
```

### Active Zone Manager Metrics (Example - BTC/USDT)
```
Total Activations: 100
Max Active Zones: 8
Avg Active Zones: 3.34
Zones Detected: 100
Candidates Scored: 1925
Orders Placed: 144
```

## No Strategy Logic Changes

Confirmed **NO changes** to:
- ❌ Scoring thresholds (min_setup_score, freshness, legout, base_time)
- ❌ Gating rules (curve/trend alignment, equilibrium handling)
- ❌ R-multiple requirements (min_reward_risk = 3.0)
- ❌ Entry/exit logic (limit orders, TTL, slippage, fees)
- ❌ Trade management (breakeven, take profit levels)

Only infrastructure changes to fix hashability issue.

## Files Changed

### 1. `strategies/supply_demand_v1/runner.py`
**Lines modified:** ~50 lines
- Added `make_zone_id()` helper (line 100-129)
- Updated `ltf_zones_by_creation` structure (line 1028-1035)
- Changed `active_zones` from set to dict (line 1039)
- Added activation tracking metrics (line 1041-1045)
- Updated activation logic (line 1267-1269)
- Updated removal logic with safe pattern (line 1271-1280)
- Updated iteration to use `items()` (line 1285)
- Added runtime sanity metrics output (line 1434-1463)

### 2. `tests/test_active_zone_manager.py`
**Status:** NEW FILE
**Lines:** 243 lines
- 3 test functions validating the fix
- All tests pass with pytest

## Performance Impact

**No performance degradation:**
- Dict lookup: O(1) average case (same as set)
- Zone ID generation: O(1) per zone (done once during bucketing)
- Memory overhead: Minimal (zone_id strings are small)
- Activation tracking: O(1) counter updates

## Backward Compatibility

✅ **Fully backward compatible:**
- No changes to config schema
- No changes to artifact schema
- No changes to strategy parameters
- Existing experiments run unchanged

## Acceptance Criteria

✅ **All deliverables met:**

- [x] **A) Replace active_zones set with dict**
  - Helper `make_zone_id()` added
  - `ltf_zones_by_creation` stores tuples
  - `active_zones: Dict[str, Zone]` implemented
  - Activation: `active_zones[zone_id] = zone`
  - Removal: safe pattern (collect then delete)
  - Iteration: `for zone_id, zone in active_zones.items()`

- [x] **B) Ensure removal logic is safe**
  - No dict mutation while iterating
  - Collect `zone_ids_to_remove` first
  - Delete after loop completes

- [x] **C) Add runtime sanity metrics**
  - Tracks `total_activations`
  - Tracks `max_active_zones`
  - Tracks `avg_active_zones`
  - Prints metrics after each symbol
  - Warns if activations=0 but zones>0

- [x] **D) Add targeted unit test**
  - Generates at least 1 zone (44 zones detected)
  - Validates `ltf_zones_by_creation` keys
  - Confirms active_zones non-empty
  - Confirms orders_placed > 0 (12 orders)
  - All assertions pass

- [x] **E) No strategy logic changes**
  - No threshold changes
  - No gating changes
  - No scoring changes

## Conclusion

The active zone manager regression has been **fully resolved**. Orders are now being placed correctly (257 orders in default config vs. 0 before), with no integrity violations and no strategy logic changes. The fix uses a stable dict-based tracking system that avoids Python's undefined behavior with mutable objects in sets.

All tests pass and the implementation is production-ready.
