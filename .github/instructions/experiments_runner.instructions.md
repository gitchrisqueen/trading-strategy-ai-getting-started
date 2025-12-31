---
applyTo:
  - "scripts/**/*.py"
  - "experiments/**/*.yml"
  - "experiments/**/*.yaml"
  - "artifacts/**"
---

# Experiments and Runner Instructions

These instructions apply to experiment runner scripts, YAML configs, and artifact generation.

## Runner Must Write Artifacts with Complete Schema

**Critical Rule**: Every experiment run must generate a complete set of artifacts with consistent schema.

### Required Artifact Files

After each experiment run, the following files must exist in `./artifacts/sd_v1/<timestamp>_<hash>/`:

1. **summary.json** - Aggregate metrics + per-symbol breakdown
2. **trades.csv** - All trades with entry/exit/R-multiples/scores
3. **zones.csv** - All detected zones with scoring inputs
4. **run_manifest.json** - Git commit hash, config used, Python version, timestamp
5. **violations.json** - Integrity check results (look-ahead bias, R violations)

### Why Complete Artifacts Matter

- **Reproducibility**: Another developer can reproduce the exact run
- **Comparison**: Compare strategy performance before/after code changes
- **Debugging**: Investigate unexpected behavior using detailed trade logs
- **Integrity**: Validate backtest quality with violation reports
- **Audit trail**: Track what config and code version produced what results

### Artifact Schema: summary.json

```json
{
  "aggregate_metrics": {
    "total_trades": 150,
    "total_zones_detected": 450,
    "overall_win_rate": 0.62,
    "average_r_multiple": 2.85,
    "total_profit": 4250.50,
    "max_drawdown": -850.30,
    "sharpe_ratio": 1.42,
    "total_symbols": 5,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "initial_capital": 10000,
    "final_capital": 14250.50
  },
  "per_symbol_metrics": {
    "BTC/USDT": {
      "trades": 35,
      "zones": 105,
      "win_rate": 0.65,
      "avg_r": 3.10,
      "profit": 1250.00
    },
    "ETH/USDT": {
      "trades": 28,
      "zones": 89,
      "win_rate": 0.58,
      "avg_r": 2.75,
      "profit": 980.25
    }
    // ... more symbols
  },
  "config_snapshot": {
    "min_setup_score": 6.0,
    "min_reward_risk": 3.0,
    "risk_pct": 0.02,
    "htf_tf": "4h",
    "itf_tf": "1h",
    "ltf_tf": "15m"
  }
}
```

### Artifact Schema: trades.csv

Required columns:

- `symbol` - Trading pair (e.g., "BTC/USDT")
- `side` - "LONG" or "SHORT"
- `entry_price` - Actual entry price (with slippage/fees)
- `stop_loss` - Stop loss price
- `take_profit` - Take profit target price
- `position_size` - Number of units/contracts
- `planned_r` - Planned reward-to-risk ratio (e.g., 3.0)
- `realized_r` - Actual R achieved (e.g., 2.8 if stopped out early)
- `entry_time` - Timestamp or candle index of entry
- `exit_time` - Timestamp or candle index of exit
- `exit_reason` - "STOP_LOSS", "TAKE_PROFIT", "BREAKEVEN", "TIMEOUT"
- `score` - Setup score (e.g., 7.5)
- `curve_state` - HTF curve: "LOW", "EQ", "HIGH"
- `trend_state` - ITF trend: "UP", "DOWN", "SIDEWAYS"
- `profit_loss` - Dollar profit/loss
- `entry_idx` - Candle index when entered
- `exit_idx` - Candle index when exited

### Artifact Schema: zones.csv

Required columns:

- `symbol` - Trading pair
- `zone_type` - "DEMAND" or "SUPPLY"
- `proximal` - Proximal line price
- `distal` - Distal line price
- `base_start_idx` - Candle index where base starts
- `base_end_idx` - Candle index where base ends
- `base_len` - Number of candles in base
- `legout_end_idx` - Candle index where leg-out ends
- `legout_return` - Percentage return of leg-out (e.g., 0.08 for 8%)
- `created_at` - Candle index when zone was created
- `freshness_touches` - Number of times price revisited zone
- `is_fresh` - Boolean: zone never revisited
- `score` - Total setup score (0-10)
- `freshness_score` - Freshness component (0/1.5/3)
- `legout_strength_score` - Leg-out component (0/1/2)
- `base_time_score` - Base time component (0/1/2)
- `profit_zone_score` - Profit zone component (0/1.5/3)

### Artifact Schema: run_manifest.json

```json
{
  "timestamp": "2024-12-31T12:00:00Z",
  "git_commit_hash": "abc1234567890def",
  "git_branch": "main",
  "git_is_dirty": false,
  "config_file": "experiments/sd_v1_default.yaml",
  "python_version": "3.11.5",
  "dependencies": {
    "pandas": "2.0.3",
    "numpy": "1.24.3",
    "pyyaml": "6.0"
  },
  "run_duration_seconds": 125.5
}
```

### Artifact Schema: violations.json

```json
{
  "planned_r_violations": [
    {
      "symbol": "BTC/USDT",
      "trade_idx": 5,
      "planned_r": 2.5,
      "min_r_required": 3.0,
      "message": "Trade planned_r (2.5) below minimum (3.0)"
    }
  ],
  "entry_timing_issues": [
    {
      "symbol": "ETH/USDT",
      "trade_idx": 12,
      "entry_idx": 100,
      "zone_created_at": 105,
      "message": "Entry (100) before zone creation (105) - look-ahead bias"
    }
  ],
  "r_calculation_errors": [],
  "summary": {
    "total_violations": 2,
    "trades_analyzed": 150,
    "clean_trades": 148
  }
}
```

## Configs Must Be Clearly Named and Documented

### Config File Naming

Use descriptive names that indicate scope and purpose:

**Good names:**
- `sd_v1_default.yaml` - Default config (quick testing)
- `sd_v1_wide_symbols.yaml` - Comprehensive test (15 symbols)
- `sd_v1_high_score.yaml` - High score threshold experiment
- `sd_v1_2r_exit.yaml` - 2R take-profit instead of 3R

**Bad names (DON'T USE):**
- `config.yaml` - Not descriptive
- `test1.yaml` - Unclear purpose
- `experiment.yaml` - Generic

### Config File Structure

```yaml
# ============================================================
# Supply & Demand V1 Experiment Configuration
# ============================================================
# Description: Default experiment for quick validation
# Symbols: 5 major pairs (BTC, ETH, MATIC, SOL, AVAX)
# Duration: 1 year (2023)
# Expected runtime: 1-2 minutes
# ============================================================

experiment:
  name: "sd_v1_default"
  description: "Default Supply & Demand V1 backtest with 5 symbols"

data:
  symbols:
    - "BTC/USDT"
    - "ETH/USDT"
    - "MATIC/USDT"
    - "SOL/USDT"
    - "AVAX/USDT"
  start_date: "2023-01-01"
  end_date: "2023-12-31"
  
  # Data generation (for synthetic candles)
  candles_per_symbol: 10000
  synthetic_seed: 42  # For reproducibility

capital:
  initial_capital: 10000
  risk_pct: 0.02  # Risk 2% per trade

timeframes:
  htf: "4h"   # Higher timeframe (curve analysis)
  itf: "1h"   # Intermediate timeframe (trend)
  ltf: "15m"  # Lower timeframe (zone detection)

strategy:
  # Zone detection
  min_base_candles: 1
  max_base_candles: 6
  proximal_mode: "body"  # or "wick"
  
  # Scoring thresholds
  min_setup_score: 6.0
  freshness_touches_best: 0
  freshness_touches_good: 1
  base_time_best: 3
  base_time_good: 6
  legout_strength_high_threshold: 0.10  # 10%
  legout_strength_mid_threshold: 0.05   # 5%
  
  # Trade management
  min_reward_risk: 3.0
  breakeven_at_r: 2.0
  take_profit_at_r: 3.0
  stop_buffer_pct: 0.001  # 0.1%
  
  # Entry
  entry_mode: "LIMIT"
  ttl_bars: 10
  
  # Multi-timeframe gating
  allow_eq_trades: true
  eq_requires_trend_alignment: true
  eq_min_setup_score_bonus: 1.0
  
  # Trend detection
  pivot_len: 5
  pivots_to_consider: 4

costs:
  fees_bps: 10.0      # 0.1% (10 basis points)
  slippage_bps: 5.0   # 0.05% (5 basis points)

output:
  artifacts_dir: "./artifacts/sd_v1"
  write_summary: true
  write_trades: true
  write_zones: true
  write_manifest: true
  write_violations: true
```

### Config Documentation Requirements

Every config file should include:

1. **Header comment** - Describe purpose, scope, runtime
2. **Section comments** - Explain groups of related parameters
3. **Inline comments** - Document non-obvious values
4. **Examples** - Show valid value ranges where helpful

### Example: Well-Documented Config Section

```yaml
# ============================================================
# Scoring Thresholds
# ============================================================
# These thresholds determine how many points each odds enhancer
# contributes to the total setup score (0-10 scale).
#
# Freshness: 3 points (fresh), 1.5 points (1 touch), 0 points (2+ touches)
# Leg-out strength: 2 points (>=10%), 1 point (>=5%), 0 points (<5%)
# Base time: 2 points (<=3 candles), 1 point (4-6 candles), 0 points (>6)
# Profit zone: 3 points (R>=3), 1.5 points (R>=2), 0 points (R<2)
#
# Min setup score: Minimum total score to take a trade (default 6.0)
# ============================================================

scoring:
  min_setup_score: 6.0
  freshness_touches_best: 0    # Fresh zone (never touched)
  freshness_touches_good: 1    # Tested once
  base_time_best: 3            # Tight consolidation
  base_time_good: 6            # Acceptable consolidation
  legout_strength_high: 0.10   # Strong breakout (10%+)
  legout_strength_mid: 0.05    # Moderate breakout (5%+)
```

## Do Not Break CLI Flags or Artifact Schema Without Updating Docs/Tests

### CLI Flags (scripts/run_supply_demand_v1.py)

Current CLI interface:

```bash
python scripts/run_supply_demand_v1.py --config <path_to_yaml>
```

**If adding new flags:**

1. Update `argparse` in `scripts/run_supply_demand_v1.py`
2. Update docstring and help text
3. Update `README.md` "How to Run Experiments" section
4. Update `docs/PROJECT_CONTEXT.md` if flag affects setup/workflow
5. Add tests in `tests/test_runner.py`

**Example: Adding a verbose flag**

```python
parser.add_argument(
    '--verbose', '-v',
    action='store_true',
    help='Print detailed progress during backtest execution'
)
```

Then update:
- `strategies/supply_demand_v1/README.md` (add to CLI examples)
- `tests/test_runner.py` (test with `--verbose` flag)

### Artifact Schema Changes

**If adding new fields to artifacts:**

1. **Add fields, don't remove** - Maintain backward compatibility
2. **Update schema documentation** in this file and `strategies/supply_demand_v1/README.md`
3. **Update parsing code** in any scripts that read artifacts
4. **Add tests** to validate new fields are populated
5. **Version the schema** if making breaking changes (e.g., rename field)

**Example: Adding a new field to trades.csv**

```python
# In runner.py
trades_df = pd.DataFrame([
    {
        'symbol': trade['symbol'],
        'entry_price': trade['entry'],
        # ... existing fields
        'new_field': trade['new_value'],  # NEW FIELD
    }
    for trade in all_trades
])
```

Then update:
- This file (artifact schema documentation)
- `strategies/supply_demand_v1/README.md` (trades.csv schema table)
- `tests/test_runner.py` (assert 'new_field' in trades_df.columns)

### Breaking Changes Require Coordination

**If you must make a breaking change:**

1. **Discuss in issue/PR** - Explain why it's necessary
2. **Version the change** - Add version field to manifest, change folder name
3. **Provide migration path** - Script to convert old artifacts to new format
4. **Update all documentation** - Search repo for references to old schema
5. **Update all tests** - Ensure tests work with new schema

## Runner Usage Patterns

### Running an Experiment

```bash
# Default experiment (quick validation)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Wide symbols experiment (comprehensive)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml
```

### Output Location

Artifacts are written to:

```
./artifacts/sd_v1/<timestamp>_<short_hash>/
```

Example:
```
./artifacts/sd_v1/20241231_120000_abc1234/
├── summary.json
├── trades.csv
├── zones.csv
├── run_manifest.json
└── violations.json
```

### Programmatic Usage

```python
from strategies.supply_demand_v1.runner import run_backtest_experiment, write_artifacts, create_artifacts_folder

# Run experiment
result = run_backtest_experiment("experiments/sd_v1_default.yaml")

# Access results
print(f"Total trades: {result.aggregate_metrics['total_trades']}")
print(f"Win rate: {result.aggregate_metrics['overall_win_rate']:.2%}")
print(f"Total zones: {result.aggregate_metrics['total_zones_detected']}")

# Write artifacts
artifacts_dir = create_artifacts_folder()
write_artifacts(result, artifacts_dir)
print(f"Artifacts written to: {artifacts_dir}")
```

## Comparing Runs Between PRs

Use artifacts to validate that code changes don't degrade performance:

### Step 1: Run Baseline (Before PR)

```bash
git checkout main
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Artifacts: artifacts/sd_v1/20241231_120000_abc1234/
```

### Step 2: Run After Changes (In PR Branch)

```bash
git checkout feature/my-improvement
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Artifacts: artifacts/sd_v1/20241231_130000_def5678/
```

### Step 3: Compare Results

```bash
# Compare summary.json files
diff \
  artifacts/sd_v1/20241231_120000_abc1234/summary.json \
  artifacts/sd_v1/20241231_130000_def5678/summary.json

# Or use jq for structured comparison
jq '.aggregate_metrics' artifacts/sd_v1/20241231_120000_abc1234/summary.json
jq '.aggregate_metrics' artifacts/sd_v1/20241231_130000_def5678/summary.json
```

### Step 4: Check for Violations

```bash
# Ensure new code doesn't introduce integrity violations
cat artifacts/sd_v1/20241231_130000_def5678/violations.json
# Should have empty arrays: "planned_r_violations": [], "entry_timing_issues": []
```

### Step 5: Document Differences in PR

Include comparison in PR description:

```markdown
## Performance Comparison

### Before (main branch)
- Total trades: 150
- Win rate: 62%
- Avg R: 2.85
- Total profit: $4,250

### After (this PR)
- Total trades: 165 (+15)
- Win rate: 65% (+3%)
- Avg R: 2.95 (+0.10)
- Total profit: $5,100 (+$850)

### Violations
- Before: 0 violations
- After: 0 violations ✅
```

## Creating New Experiment Configs

### Step 1: Copy Existing Config

```bash
cp experiments/sd_v1_default.yaml experiments/sd_v1_my_experiment.yaml
```

### Step 2: Edit Parameters

Modify the copied file:
- Update experiment name and description
- Change symbols, date range, or capital as needed
- Adjust strategy parameters (scoring, R-multiples, etc.)
- Update comments to reflect changes

### Step 3: Test the Config

```bash
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_my_experiment.yaml
```

### Step 4: Validate Artifacts

```bash
ls -l artifacts/sd_v1/<latest_timestamp>/
# Should see: summary.json, trades.csv, zones.csv, run_manifest.json, violations.json

cat artifacts/sd_v1/<latest_timestamp>/violations.json
# Should have empty violation arrays
```

### Step 5: Document the Config

Add entry to `strategies/supply_demand_v1/README.md` if it's a useful reference config.

## Runner Implementation Notes

### File: scripts/run_supply_demand_v1.py

**Purpose**: CLI wrapper for experiment runner

**Responsibilities**:
- Parse command-line arguments
- Load config file
- Call runner functions
- Display results

**Don't add:**
- Strategy logic (belongs in `strategy.py`)
- Heavy computation (belongs in `runner.py`)
- Data processing (belongs in `runner.py`)

### File: strategies/supply_demand_v1/runner.py

**Purpose**: Core experiment execution and artifact generation

**Responsibilities**:
- Load YAML config
- Generate or load candle data
- Run backtest using strategy functions
- Collect results (zones, trades, metrics)
- Run integrity checks
- Write artifacts with consistent schema
- Return structured result object

**Key functions**:
- `run_backtest_experiment(config_path) -> ExperimentResult`
- `write_artifacts(result, artifacts_dir)`
- `create_artifacts_folder() -> Path`
- `load_config(config_path) -> dict`
- `generate_synthetic_candles(params) -> list`

### Result Object Structure

```python
class ExperimentResult:
    aggregate_metrics: dict        # Overall performance across all symbols
    per_symbol_metrics: dict       # Breakdown by symbol
    all_trades: list              # List of all trade dicts
    all_zones: list               # List of all zone dicts
    violations: dict              # Integrity check violations
    config_snapshot: dict         # Config used for this run
    run_metadata: dict            # Timestamp, git hash, Python version
```

## Artifact Generation Best Practices

### 1. Use Pandas for CSV Writing

```python
import pandas as pd

trades_df = pd.DataFrame(all_trades)
trades_df.to_csv(artifacts_dir / 'trades.csv', index=False)
```

### 2. Use JSON for Structured Data

```python
import json

with open(artifacts_dir / 'summary.json', 'w') as f:
    json.dump(summary, f, indent=2)
```

### 3. Include Metadata in Manifest

```python
import subprocess
from datetime import datetime

manifest = {
    'timestamp': datetime.now().isoformat(),
    'git_commit_hash': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
    'python_version': sys.version,
    'config_file': str(config_path),
}
```

### 4. Validate Before Writing

```python
# Check that all required fields are present
required_fields = ['entry_price', 'stop_loss', 'take_profit', 'planned_r']
for trade in all_trades:
    for field in required_fields:
        if field not in trade:
            raise ValueError(f"Trade missing required field: {field}")
```

## Testing the Runner

### Unit Tests

```bash
poetry run pytest tests/test_runner.py -v
```

### Integration Tests

```bash
# Run actual experiment and validate artifacts
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
cat artifacts/sd_v1/<latest>/violations.json  # Check for violations
```

### Test Cases to Cover

- Config loading (valid YAML, missing fields, invalid values)
- Backtest execution (returns result object with expected structure)
- Artifact generation (all files created, schemas match)
- Integrity checks (violations detected when expected)
- Error handling (bad config, missing files, corrupted data)

## Common Runner Issues and Solutions

### Issue: Artifacts Not Generated

**Symptoms**: Runner completes but artifacts folder is empty

**Solutions**:
- Check permissions on `./artifacts/` folder
- Verify artifact writing logic is called
- Look for exceptions in output (might be silently caught)
- Ensure `write_summary=true` etc. in config

### Issue: Violations Not Empty

**Symptoms**: `violations.json` reports planned_r or timing issues

**Solutions**:
- Review strategy logic for minimum R enforcement
- Check zone creation timing vs. trade entry timing
- Verify R-multiple calculations (reward/risk formula)
- Run specific integrity tests to isolate issue

### Issue: Inconsistent Results Between Runs

**Symptoms**: Same config produces different metrics on each run

**Solutions**:
- Ensure synthetic data uses fixed seed
- Check for non-deterministic logic (random, time-based)
- Verify freshness tracking doesn't depend on run order
- Run integrity checks to catch look-ahead bias

### Issue: Runtime Too Slow

**Symptoms**: Experiment takes >5 minutes for default config

**Solutions**:
- Reduce `candles_per_symbol` in config (for synthetic data)
- Profile code to find bottlenecks (`python -m cProfile`)
- Cache expensive computations (indicator calculations)
- Consider vectorizing zone detection or scoring

## Runner Quality Checklist

Before merging changes to runner or configs:

- [ ] CLI flags documented in help text and README
- [ ] Config files have descriptive names and header comments
- [ ] All required artifact files are generated
- [ ] Artifact schemas match documentation
- [ ] Integrity checks run and report violations
- [ ] Tests pass: `poetry run pytest tests/test_runner.py -v`
- [ ] Experiment runs successfully: `python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml`
- [ ] Violations are empty (or expected): `cat artifacts/sd_v1/<latest>/violations.json`
- [ ] Run manifest includes git hash and timestamp
- [ ] Performance is acceptable (< 2 minutes for default config)
