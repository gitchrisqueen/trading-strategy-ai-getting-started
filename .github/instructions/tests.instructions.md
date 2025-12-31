---
applyTo:
  - "tests/**/*.py"
---

# Test Instructions

These instructions apply to all test files under `tests/`.

## Tests Must Be Deterministic

**Critical Rule**: Tests must produce identical results on every run.

### Why Determinism Matters

- **CI reliability**: Flaky tests block PRs and waste developer time
- **Reproducibility**: Other developers must be able to reproduce failures
- **Debugging**: Non-deterministic failures are impossible to debug
- **Regression detection**: Tests must reliably catch bugs introduced by changes

### How to Ensure Determinism

1. **Use fixed test data**: Define candle arrays, zones, and trade plans explicitly in test setup
2. **Seed random number generators**: If using random data, seed the RNG:
   ```python
   import random
   random.seed(42)
   np.random.seed(42)
   ```
3. **Avoid time-based data**: Don't use `datetime.now()` or `time.time()` without mocking
4. **No external dependencies**: Don't fetch data from APIs or files that might change
5. **Fixed parameter values**: Don't randomize test parameters

### Example: Good Deterministic Test

```python
def test_zone_detection_dbr():
    """Test DBR (demand) zone detection with fixed candles"""
    candles = [
        {'open': 110, 'high': 110, 'low': 100, 'close': 100},  # Drop
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},   # Base 1
        {'open': 101, 'high': 102, 'low': 99, 'close': 100},   # Base 2
        {'open': 100, 'high': 110, 'low': 100, 'close': 110},  # Rally
    ]
    
    zones = detect_supply_demand_zones(candles, min_base_candles=1, max_base_candles=6)
    
    assert len(zones) == 1
    assert zones[0]['zone_type'] == ZoneType.DEMAND
    assert zones[0]['proximal'] == 102.0
    assert zones[0]['distal'] == 99.0
```

### Example: Bad Non-Deterministic Test (DON'T DO THIS)

```python
def test_zone_detection_random():
    """BAD: Uses random data without seed"""
    candles = generate_random_candles(n=100)  # Different every run!
    zones = detect_supply_demand_zones(candles, min_base_candles=1, max_base_candles=6)
    assert len(zones) > 0  # Vague assertion, might fail randomly
```

## Prefer Unit Tests for Core Logic

**Test hierarchy** (in order of preference):

1. **Unit tests**: Test individual functions in isolation (zone detection, scoring, freshness)
2. **Integration tests**: Test interactions between modules (runner + strategy, MTF gating)
3. **End-to-end tests**: Test complete workflows (experiment runs, artifact generation)
4. **Notebook tests**: Validate that notebooks run without errors (slowest, least granular)

### Why Unit Tests Are Preferred

- **Fast**: Run in milliseconds, not seconds
- **Focused**: Pinpoint exact failure location
- **Granular**: Test edge cases thoroughly
- **Independent**: Don't depend on other modules
- **Debuggable**: Easy to step through in debugger

### Example Test Organization

```python
# Unit tests for zone detection
def test_classify_boring_candle():
    """Test boring candle classification (body <= 50% of range)"""
    # ...

def test_classify_exciting_candle():
    """Test exciting candle classification (body > 50% of range)"""
    # ...

def test_detect_dbr_zone():
    """Test Drop-Base-Rally demand zone detection"""
    # ...

def test_detect_rbd_zone():
    """Test Rally-Base-Drop supply zone detection"""
    # ...

# Integration tests for multi-timeframe gating
def test_curve_classification_with_fresh_zones():
    """Test HTF curve classification using detected zones"""
    # ...

def test_gating_blocks_demand_at_high_curve():
    """Test that demand zones are blocked when curve=HIGH"""
    # ...
```

## Test Coverage by Module

### Zone Detection (`test_supply_demand_zones.py`)

**What to test:**
- Candle classification (boring vs. exciting, edge cases like doji)
- DBR pattern detection (leg-in, base, leg-out)
- RBD pattern detection (leg-in, base, leg-out)
- Proximal/distal calculations (body mode, wick mode)
- Base length validation (min/max candles)
- Freshness tracking (initial state, touches, updates)

**Example test cases:**
- Single DBR with 2-candle base
- Single RBD with 6-candle base
- Multiple overlapping zones
- No zones detected (all exciting or all boring candles)
- Edge case: doji candles (open=high=low=close)
- Edge case: zero-length range

### Strategy (`test_supply_demand_strategy.py`)

**What to test:**
- Odds enhancer scoring (freshness, leg-out strength, base time, profit zone)
- Trade plan generation (entry, stop, target, position size)
- R-multiple calculations (reward/risk ratio)
- Minimum R enforcement (plans rejected if R < min_reward_risk)
- Trade management (breakeven moves, take-profit exits)

**Example test cases:**
- Fresh zone (0 touches) scores 3 points
- 1-touch zone scores 1.5 points
- 2+ touch zone scores 0 points
- Leg-out >=10% scores 2 points
- Base <=3 candles scores 2 points
- Trade plan with R=3.0 (minimum)
- Trade plan rejected with R=2.5 (below minimum)
- Breakeven move at 2R profit

### Multi-Timeframe Gating (`test_supply_demand_mtf_gating.py`)

**What to test:**
- Curve classification (LOW, EQ, HIGH based on fresh zones)
- Trend detection (UP, DOWN, SIDEWAYS based on pivots)
- Gating rules (demand at LOW curve, supply at HIGH curve)
- Equilibrium handling (requires trend alignment + score bonus)
- Edge cases (no fresh zones, no pivots)

**Example test cases:**
- Demand zone allowed at LOW curve + UP trend
- Demand zone blocked at HIGH curve
- Supply zone allowed at HIGH curve + DOWN trend
- Supply zone blocked at LOW curve
- Equilibrium trade allowed with trend alignment and high score
- Equilibrium trade blocked with SIDEWAYS trend

### Fill Logic (`test_supply_demand_fill_logic.py`)

**What to test:**
- Limit order fills (demand fills when low <= entry, supply fills when high >= entry)
- Order expiry (TTL after `ttl_bars` candles)
- Slippage and fees application (actual_entry = entry * (1 + slippage + fees))
- Stop loss hits (exit when price crosses stop)
- Take profit hits (exit at target)

**Example test cases:**
- Limit buy fills when candle low touches entry
- Limit buy doesn't fill when candle low is above entry
- Order cancels after TTL expires
- Stop loss triggered on bearish candle
- Take profit triggered at 3R target

### Integrity (`test_supply_demand_integrity.py`)

**What to test:**
- Look-ahead bias detection (entries must occur after zone creation)
- R-multiple accuracy (planned_R matches calculation)
- Minimum R enforcement (all trades have R >= min_reward_risk)
- Entry timing (entries after zone legout_end_idx)

**Example test cases:**
- Valid trade: entry_idx > zone.legout_end_idx
- Invalid trade: entry_idx <= zone.legout_end_idx (look-ahead)
- Valid R calculation: |target - entry| / |entry - stop| == 3.0
- Invalid R: planned_R = 2.5 but min_reward_risk = 3.0

### Runner (`test_runner.py`)

**What to test:**
- Experiment config loading (YAML parsing)
- Backtest execution (returns ExperimentResult)
- Artifact generation (summary.json, trades.csv, zones.csv)
- Artifact schema validation (required fields present)
- Integrity check execution (violations detected)

**Example test cases:**
- Config loads with valid YAML
- Experiment runs and returns result object
- Artifacts folder created with timestamp
- summary.json contains aggregate_metrics and per_symbol_metrics
- trades.csv contains required columns (entry, stop, target, planned_R)
- violations.json reports empty arrays (no violations)

### Notebooks (`test_notebooks.py`)

**What to test:**
- Notebooks execute without errors
- Notebooks in `single-backtest/` run to completion
- Grid search notebooks are skipped (honor pragmas)

**Example test cases:**
- `bitcoin-ma.ipynb` runs successfully
- `supply_demand_v1_backtest.ipynb` runs successfully
- Notebooks with `# @ts skip-test` pragma are skipped

## Add Fixtures Minimally

**Fixtures are useful, but use them sparingly:**

### When to Use Fixtures

- **Shared test data** used by multiple tests (e.g., standard candle set)
- **Complex setup** that would clutter test bodies
- **Test isolation** (e.g., temporary directories, database connections)

### When NOT to Use Fixtures

- **Test-specific data**: If only one test uses it, define inline
- **Simple data**: If data is 3-5 lines, inline is clearer than fixture
- **Overuse leads to confusion**: Developers have to jump between files to understand tests

### Example: Good Fixture Usage

```python
@pytest.fixture
def standard_candles():
    """Standard 10-candle dataset for zone detection tests"""
    return [
        {'open': 100, 'high': 105, 'low': 95, 'close': 102},
        {'open': 102, 'high': 108, 'low': 100, 'close': 106},
        # ... 8 more candles
    ]

def test_zone_detection_with_standard_candles(standard_candles):
    zones = detect_supply_demand_zones(standard_candles, min_base_candles=1, max_base_candles=6)
    assert len(zones) == 2
```

### Example: Bad Fixture Overuse (DON'T DO THIS)

```python
@pytest.fixture
def candle1():  # Too granular
    return {'open': 100, 'high': 105, 'low': 95, 'close': 102}

@pytest.fixture
def candle2():  # Too granular
    return {'open': 102, 'high': 108, 'low': 100, 'close': 106}

def test_zone_detection(candle1, candle2):  # Confusing
    candles = [candle1, candle2]
    # ...
```

## Test Naming Conventions

**Use descriptive names that explain what is being tested:**

### Good Test Names

- `test_classify_boring_candle_with_50_percent_body`
- `test_detect_dbr_zone_with_2_candle_base`
- `test_freshness_tracking_increments_touches`
- `test_trade_plan_rejected_when_r_below_minimum`
- `test_demand_zone_blocked_at_high_curve`

### Bad Test Names (DON'T DO THIS)

- `test_zones()`
- `test_scoring()`
- `test_case_1()`
- `test_it_works()`

**Rule of thumb**: A developer should understand what the test validates just from reading the name.

## Assertion Best Practices

### Use Exact Assertions

**DO:**
```python
assert zone['proximal'] == 102.0
assert zone['distal'] == 99.0
assert zone['base_len'] == 2
```

**DON'T:**
```python
assert zone['proximal'] > 100  # Too vague
assert 100 < zone['proximal'] < 105  # Range assertions hide actual values
assert zone['base_len'] >= 1  # Doesn't verify expected value
```

### Use Descriptive Assertion Messages

**DO:**
```python
assert zone['zone_type'] == ZoneType.DEMAND, f"Expected DEMAND zone, got {zone['zone_type']}"
assert len(zones) == 2, f"Expected 2 zones, detected {len(zones)}: {zones}"
```

**DON'T:**
```python
assert zone['zone_type'] == ZoneType.DEMAND  # No context if fails
```

### Test Edge Cases Explicitly

**DO:**
```python
def test_zone_detection_with_all_boring_candles():
    """No zones should be detected if all candles are boring"""
    candles = [
        {'open': 100, 'high': 101, 'low': 100, 'close': 100.5},  # Boring
        {'open': 100.5, 'high': 101, 'low': 100, 'close': 100.3},  # Boring
    ]
    zones = detect_supply_demand_zones(candles, min_base_candles=1, max_base_candles=6)
    assert len(zones) == 0, "No zones should be detected with only boring candles"

def test_zone_detection_with_doji_candle():
    """Doji candles (open=high=low=close) should be classified as boring"""
    candles = [
        {'open': 100, 'high': 100, 'low': 100, 'close': 100},  # Doji
    ]
    # Test that doji is classified correctly
    # ...
```

## Running Tests Efficiently

### Run All Tests

```bash
poetry run pytest
```

### Run Specific Test File

```bash
poetry run pytest tests/test_supply_demand_zones.py -v
```

### Run Specific Test

```bash
poetry run pytest tests/test_supply_demand_zones.py::test_detect_dbr_zone -v
```

### Run Tests Matching Pattern

```bash
poetry run pytest -k "freshness" -v  # Runs all tests with "freshness" in name
```

### Run Tests with Coverage

```bash
poetry run pytest --cov=strategies.supply_demand_v1 --cov-report=html
```

### Run Tests in Parallel (If Installed)

```bash
poetry run pytest -n auto  # Requires pytest-xdist
```

## Test Organization Guidelines

### File Structure

```
tests/
├── test_supply_demand_zones.py           # Zone detection, classification, freshness
├── test_supply_demand_strategy.py        # Scoring, trade planning, management
├── test_supply_demand_mtf_gating.py      # Multi-timeframe gating logic
├── test_supply_demand_fill_logic.py      # Order fills, TTL, slippage
├── test_supply_demand_integrity.py       # Look-ahead, R-multiple enforcement
├── test_runner.py                        # Experiment runner, artifact generation
└── test_notebooks.py                     # Notebook execution tests
```

### Test File Contents

Each test file should:
1. Import only what it needs (no wildcard imports)
2. Group related tests with comments or test classes
3. Keep tests independent (one test failure shouldn't cascade)
4. Use clear, descriptive variable names
5. Clean up after itself (no leftover files or state)

## Common Testing Anti-Patterns to Avoid

### ❌ Testing Implementation Details

**DON'T:**
```python
def test_zone_detection_uses_for_loop():
    """BAD: Tests how it's implemented, not what it does"""
    # ...
```

**DO:**
```python
def test_zone_detection_returns_dbr_zones():
    """Tests behavior, not implementation"""
    # ...
```

### ❌ One Giant Test

**DON'T:**
```python
def test_entire_strategy():
    """Tests everything in one function (impossible to debug)"""
    # 500 lines of setup, assertions, and logic
```

**DO:**
```python
def test_zone_detection():
    # ...

def test_zone_scoring():
    # ...

def test_trade_planning():
    # ...
```

### ❌ Tests That Depend on Order

**DON'T:**
```python
# test_a.py
def test_create_zone():
    global zone
    zone = create_zone()

# test_b.py
def test_score_zone():
    # Depends on test_a running first (BAD!)
    score = score_zone(zone)
```

**DO:**
```python
def test_score_zone():
    zone = create_zone()  # Independent setup
    score = score_zone(zone)
```

### ❌ Catching Exceptions Too Broadly

**DON'T:**
```python
def test_invalid_input():
    try:
        result = some_function(bad_input)
    except:  # Catches ALL exceptions, including test failures
        pass
```

**DO:**
```python
def test_invalid_input():
    with pytest.raises(ValueError, match="Invalid input"):
        result = some_function(bad_input)
```

## When to Add New Tests

Add tests when:

1. **Adding new features**: Test the feature's behavior
2. **Fixing bugs**: Add a regression test that would have caught the bug
3. **Changing existing behavior**: Update tests to reflect new expected behavior
4. **Refactoring**: Ensure tests still pass (behavior unchanged)

## When to Update Existing Tests

Update tests when:

1. **Expected behavior changes**: Update assertions to match new behavior
2. **Test data is insufficient**: Add more edge cases or scenarios
3. **Tests are flaky**: Make tests deterministic
4. **Tests are unclear**: Improve naming, assertions, or comments

## Test Quality Checklist

Before submitting a PR with test changes:

- [ ] Tests are deterministic (produce same results every run)
- [ ] Tests are independent (don't depend on other tests)
- [ ] Tests have descriptive names (explain what is tested)
- [ ] Tests use exact assertions (not vague ranges)
- [ ] Tests cover edge cases (empty inputs, zero values, boundary conditions)
- [ ] Tests are fast (unit tests run in milliseconds)
- [ ] Tests clean up after themselves (no leftover files or state)
- [ ] All tests pass: `poetry run pytest -v`
