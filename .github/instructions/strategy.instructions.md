---
applyTo:
  - "strategies/supply_demand_v1/**/*.py"
  - "strategies/supply_demand_v1/**/*.md"
---

# Supply & Demand V1 Strategy Instructions

These instructions apply to all files under `strategies/supply_demand_v1/`.

## Strategy Design Principles

### 1. No Look-Ahead Bias

**Critical Rule**: Trading decisions must ONLY use data available at the time of the decision.

- Zone detection uses past candles only
- Trade decisions occur AFTER zone creation: `decision_idx > zone.legout_end_idx`
- Freshness tracking updates as new candles arrive, not retroactively
- All timestamps and indices must flow forward in time

**Test validation**: `tests/test_supply_demand_integrity.py` checks for look-ahead violations.

### 2. Deterministic Fills

Fill logic must be repeatable and precise:

- **Limit orders**: Fill when price touches entry level (demand: `candle.low <= entry`, supply: `candle.high >= entry`)
- **Slippage and fees**: Applied consistently (`actual_entry = entry * (1 + slippage_bps/10000 + fees_bps/10000)`)
- **TTL expiry**: Orders cancel after `ttl_bars` candles from placement
- **No partial fills**: Orders fill completely or not at all (simplified for backtesting)

**Test validation**: `tests/test_supply_demand_fill_logic.py` validates fill behavior.

### 3. Enforce Policy Gates

Strategy enforces strict rules that should NOT be bypassed:

- **Minimum R requirement**: All trades must have `reward/risk >= min_reward_risk` (default 3.0)
- **Setup score threshold**: Trades only taken if `zone.score >= min_setup_score` (default 6.0)
- **Multi-timeframe gating**: Demand zones blocked when curve=HIGH, supply zones blocked when curve=LOW, equilibrium trades require trend alignment
- **Stop placement**: Always beyond distal with buffer, never inside the zone

**DO NOT circumvent these gates unless explicitly requested in PR.**

### 4. Maintain Stable Public Interfaces

The following interfaces are consumed by runner, notebooks, and tests. **Do not change signatures or return types without updating all callers:**

#### Zone Detection
```python
def detect_supply_demand_zones(candles, min_base_candles, max_base_candles, proximal_mode="body") -> List[Zone]
```

#### Freshness Tracking
```python
def is_zone_fresh(zone, candles, current_idx) -> bool
```

#### Multi-Timeframe Analysis
```python
def find_nearest_fresh_zones_htf(zones, current_price, current_idx) -> Tuple[Optional[Zone], Optional[Zone]]
def trend_direction_itf(candles, pivot_len, pivots_to_consider) -> TrendDirection
```

#### Scoring
```python
def score_odds_enhancers(zone, opposing_zone, params) -> float
```

#### Trade Planning
```python
def build_trade_plan(zone, opposing_zone, account_size, params) -> Optional[TradePlan]
def manage_trade_plan(plan, current_price, current_idx, is_long, params) -> str  # Returns "HOLD" or "EXIT"
```

#### Runner
```python
def run_backtest_experiment(config_path) -> ExperimentResult
def write_artifacts(result, artifacts_dir)
```

## Do Not Change Scoring/Zone Logic Unless PR Explicitly Says So

The S&D strategy has carefully tuned scoring and zone detection rules:

- **Boring candle threshold**: 50% body-to-range ratio
- **Base length**: 1-6 candles
- **Freshness scoring**: 3 points (0 touches), 1.5 points (1 touch), 0 points (2+ touches)
- **Leg-out strength**: 2 points (>=10% return), 1 point (>=5% return), 0 points (<5%)
- **Base time**: 2 points (<=3 candles), 1 point (4-6 candles), 0 points (>6)
- **Profit zone**: 3 points (R>=3), 1.5 points (R>=2), 0 points (R<2)

**These are intentional design choices. DO NOT "improve" them without explicit instructions.**

If you notice a bug (e.g., incorrect calculation), fix it. But don't change thresholds or add new scoring components unless requested.

## Files and Their Responsibilities

### `strategy.py`

**Core strategy logic** - contains all zone detection, scoring, MTF analysis, and trade planning functions.

**When editing:**
- Keep functions pure and deterministic (no side effects except freshness updates)
- Add docstrings for any new public functions
- Include examples in docstrings for complex calculations
- Update type hints if adding new parameters

### `runner.py`

**Experiment runner and artifact generator** - runs backtests with YAML configs and writes artifacts.

**When editing:**
- Preserve artifact schema (summary.json, trades.csv, zones.csv, run_manifest.json, violations.json)
- Add new fields to artifacts, don't remove existing ones (backward compatibility)
- Update `run_manifest.json` with new metadata if adding features
- Run integrity checks before writing artifacts

### `README.md`

**Strategy specification** - complete documentation of strategy rules and behavior.

**When editing:**
- Update sections affected by code changes (e.g., if scoring changes, update "Odds Enhancers" section)
- Include examples and calculations for new features
- Keep parameter tables accurate (defaults, ranges, meanings)
- Add entries to "How to Run Experiments" if new configs or commands are added

### `TradingStrategySpec.md`

**Original spec document** - historical reference.

**When editing:**
- Generally avoid editing this file (it's a historical snapshot)
- Prefer updating `README.md` for current documentation

### `integrity.py`

**Integrity validation** - checks for look-ahead bias, R-multiple violations, entry timing issues.

**When editing:**
- Add new checks if introducing new trade logic
- Return violations as structured data (dicts/lists), not print statements
- Keep checks independent (each check should work without others)

### `demo_zone_detection.py`

**Standalone demo script** - shows zone detection on synthetic candles.

**When editing:**
- Keep this simple and runnable without dependencies beyond numpy/pandas
- Use as a manual testing tool, not for automated tests

## Common Patterns in This Strategy

### Candle Classification

```python
# All logic depends on boring vs. exciting classification
body = abs(candle['close'] - candle['open'])
range = candle['high'] - candle['low']
is_boring = (body <= 0.50 * range) if range > 0 else True
```

### Zone Data Structure

```python
zone = {
    'zone_type': ZoneType.DEMAND,  # or SUPPLY
    'proximal': 100.5,
    'distal': 98.0,
    'base_start_idx': 10,
    'base_end_idx': 12,
    'base_len': 3,
    'legout_end_idx': 15,
    'legout_return': 0.08,  # 8% return
    'created_at': 15,  # Index when zone was created
    'freshness_touches': 0,
    'is_fresh': True,
    'score': 0.0,  # Populated later
}
```

### Trade Plan Data Structure

```python
plan = {
    'zone': zone,
    'entry_price': 100.5,
    'stop_loss': 97.8,
    'take_profit': 108.0,
    'position_size': 50.0,
    'risk_amount': 200.0,
    'planned_r': 3.0,
    'score': 7.5,
    'placed_at_idx': 20,
    'order_state': 'PENDING',  # or 'FILLED', 'CANCELLED'
}
```

## Testing Expectations

When modifying strategy code:

1. **Run existing tests** to ensure no regression:
   ```bash
   poetry run pytest tests/test_supply_demand_zones.py -v
   poetry run pytest tests/test_supply_demand_strategy.py -v
   poetry run pytest tests/test_supply_demand_mtf_gating.py -v
   ```

2. **Add tests for new behavior**:
   - Use deterministic candle data (fixed arrays, no randomness)
   - Test edge cases (empty zones, doji candles, zero-length ranges)
   - Assert exact values, not ranges (e.g., `assert score == 7.5`, not `assert 7 < score < 8`)

3. **Run an experiment** to validate end-to-end:
   ```bash
   python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
   ```

4. **Check integrity**:
   ```bash
   cat artifacts/sd_v1/<timestamp>_<hash>/violations.json
   # Should have empty arrays for violations
   ```

## Example Modifications (What's OK vs. Not OK)

### ✅ OK to Change

- **Add new optional parameters** (with defaults that preserve existing behavior)
- **Fix bugs in calculations** (e.g., off-by-one errors, wrong formula)
- **Add new scoring components** (if explicitly requested in PR)
- **Improve performance** (e.g., vectorize calculations, cache results)
- **Add logging/debugging** (use Python logging module, not print statements)
- **Add new artifact fields** (append to existing files, don't remove fields)

### ❌ NOT OK to Change (Without Explicit Instructions)

- **Change default parameter values** (breaks reproducibility)
- **Remove or rename public functions** (breaks callers)
- **Change scoring thresholds** (defeats purpose of having thresholds)
- **Bypass R-multiple or score gates** (violates strategy rules)
- **Make fills non-deterministic** (breaks integrity checks)
- **Change artifact schema in breaking ways** (breaks parsers)
- **Refactor zone detection logic** (high risk, needs thorough testing)

## Strategy-Specific Gotchas

### Freshness Tracking Is Stateful

The `is_zone_fresh()` function mutates zone state (`zone.freshness_touches`, `zone.is_fresh`). This is intentional—freshness updates as new candles arrive.

**DO NOT refactor this to be pure functional without understanding the implications.**

### Proximal/Distal Calculations Are Precise

Proximal and distal lines are calculated using specific rules:

- **Demand proximal**: Max of candle body tops in base
- **Demand distal**: Min of candle lows across entire DBR structure
- **Supply proximal**: Min of candle body bottoms in base
- **Supply distal**: Max of candle highs across entire RBD structure

**Test these carefully if modifying.** See `tests/test_supply_demand_zones.py::test_proximal_distal_calculations`.

### Multi-Timeframe Gating Is Complex

The gating logic involves multiple conditions:

- Curve (HTF): LOW/EQ/HIGH based on nearest fresh zones
- Trend (ITF): UP/DOWN/SIDEWAYS based on pivot analysis
- Allowed combinations depend on zone type (DEMAND vs. SUPPLY)

**Don't simplify this logic without understanding all cases.** See `tests/test_supply_demand_mtf_gating.py`.

### R-Multiple Enforcement Is Non-Negotiable

Every trade must have `reward/risk >= min_reward_risk` (default 3.0). The `build_trade_plan()` function returns `None` if this isn't satisfied.

**DO NOT remove this check or allow trades with R < 3.**

## Performance Considerations

- Zone detection is O(n²) in worst case (scanning for patterns). For large datasets (10k+ candles), consider caching results.
- Freshness tracking is incremental—each new candle updates existing zones. Don't recompute freshness from scratch.
- Experiment runs generate large CSVs. Use pandas streaming if memory issues arise.

## Documentation Requirements

When making changes:

1. **Update docstrings** for modified functions
2. **Update README.md** sections affected by changes
3. **Add inline comments** for non-obvious calculations (formulas, edge cases)
4. **Update parameter tables** if adding new parameters or changing defaults
5. **Add examples** to README if adding new features (show usage, expected output)

## Questions Before Modifying?

If unsure about a change, check:

1. **Does this preserve existing behavior?** Run tests to confirm.
2. **Does this affect reproducibility?** Experiment artifacts should be deterministic.
3. **Does this change public interfaces?** Update all callers (runner, notebooks, tests).
4. **Does this bypass strategy gates?** Don't do it unless explicitly requested.
5. **Is this scoped to the current PR?** Avoid "drive-by" refactoring.
