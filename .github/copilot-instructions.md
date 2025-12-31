# GitHub Copilot Instructions

This repository provides a **getting started kit for algorithmic trading** with [Trading Strategy SDK](https://tradingstrategy.ai). It contains example backtesting notebooks, a complete Supply & Demand V1 strategy implementation, and tools for developing and testing trading strategies on both DEX and CEX data.

## Project Purpose and Default Workflow

### What This Repository Does

- **Example strategy library**: Pre-built notebooks demonstrating various trading approaches (MA crossover, ATR breakout, momentum baskets, portfolio construction)
- **Supply & Demand V1 strategy**: Production-ready zone-based trading strategy with DBR/RBD pattern detection, multi-timeframe analysis, and deterministic backtesting
- **Experiment runner**: CLI-based backtesting with YAML configs that generate machine-readable artifacts for comparing strategy performance across PRs
- **Educational resource**: Learn algorithmic trading, technical analysis, and strategy development

### Default Development Workflow

**Prefer runner/CLI + configs over editing notebooks:**

1. **For new experiments**: Create/edit YAML configs in `./experiments/` rather than duplicating notebook logic
2. **Run experiments via CLI**: `python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml`
3. **Generate artifacts**: Every run writes `summary.json`, `trades.csv`, `zones.csv`, `run_manifest.json`, `violations.json` to `./artifacts/sd_v1/<timestamp>_<hash>/`
4. **Compare results**: Use artifacts to measure impact of code changes between PRs
5. **Test with unit tests**: Run `poetry run pytest` to validate deterministic behavior before notebook runs

**Notebooks are for:**
- Exploration and prototyping new ideas
- Visualizing results (equity curves, indicator charts)
- Educational examples in documentation

**CLI runner is for:**
- Reproducible experiments
- Automated testing and CI validation
- Performance comparison across code changes

## Required Validation Steps for Any PR

Before finalizing any PR, complete these validation steps:

### 1. Run Unit Tests

```bash
poetry run pytest
```

**Focused tests for specific areas:**

```bash
# Supply & Demand strategy core logic
poetry run pytest tests/test_supply_demand_zones.py -v
poetry run pytest tests/test_supply_demand_strategy.py -v
poetry run pytest tests/test_supply_demand_mtf_gating.py -v

# Trade fill and integrity
poetry run pytest tests/test_supply_demand_fill_logic.py -v
poetry run pytest tests/test_supply_demand_integrity.py -v

# Runner and experiments
poetry run pytest tests/test_runner.py -v

# Notebooks (CI compatible)
poetry run pytest tests/test_notebooks.py -v
```

### 2. Run At Least One Experiment Config

```bash
# Quick validation (5 symbols, ~1-2 min)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Comprehensive validation (15 symbols, ~5-10 min)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml
```

### 3. Confirm Artifacts Are Generated

After experiment runs, verify the following files exist in `./artifacts/sd_v1/<timestamp>_<hash>/`:

- ✅ **summary.json** - Contains aggregate metrics + per-symbol breakdown
- ✅ **trades.csv** - All trades with entry/exit/R-multiples/scores
- ✅ **zones.csv** - All detected zones with scoring inputs
- ✅ **run_manifest.json** - Git commit hash, config used, Python version, timestamp
- ✅ **violations.json** - Integrity check results (planned_R violations, look-ahead bias flags)

**Check for violations:**

```bash
cat artifacts/sd_v1/<latest_folder>/violations.json
# Should report: "planned_r_violations": [], "entry_timing_issues": []
```

### 4. Run Linters (If Code Changed)

```bash
# Black formatter (line-length = 999)
poetry run black strategies/ tests/ scripts/

# isort imports
poetry run isort strategies/ tests/ scripts/

# flake8 (ignores E203)
poetry run flake8 strategies/ tests/ scripts/ --max-line-length=999 --extend-ignore=E203
```

## Coding Standards

### Keep PRs Small and Scoped

- **One logical change per PR**: Don't mix refactoring with new features
- **Minimal file changes**: Only edit files directly related to the issue
- **No "drive-by" refactoring**: Don't clean up unrelated code
- **Focused commits**: Each commit should represent one coherent change

### Do Not Refactor Unrelated Modules

- If you see code smell in an unrelated module, open a separate issue
- Keep your PR diff minimal and reviewable
- Preserve existing behavior unless explicitly changing it

### Add Tests for New Behavior

- **Unit tests first**: Add tests before implementing features
- **Mirror existing test patterns**: See `tests/test_supply_demand_*.py` for examples
- **Deterministic tests**: Use fixed candle data, avoid randomness without seeded RNG
- **Test edge cases**: Zero-length ranges, doji candles, empty zones, etc.

### Avoid Adding New Heavy Dependencies

- Use existing packages: pandas, numpy, pytest, pyyaml
- **Before adding new dependencies:**
  1. Check if existing packages can solve the problem
  2. Justify the dependency in PR description
  3. Ensure it's compatible with Python >=3.11,<=3.12
  4. Pin the version in `pyproject.toml`

### Code Style Conventions

- **Black formatter**: `line-length = 999` (intentionally high for compact data structures)
- **isort**: Organize imports alphabetically within sections
- **flake8**: Ignore E203 (whitespace before ':')
- **Comments**: Only add if explaining non-obvious logic or complex calculations
- **State mutations**: Acceptable in freshness tracking (`is_zone_fresh`), but document why
- **Type hints**: Preferred but not required; use when adding new public interfaces

## Where to Look First in This Repo

### Essential Documentation (Read These First)

| File | Purpose |
|------|---------|
| `docs/PROJECT_CONTEXT.md` | Project overview, setup instructions, how to run the S&D strategy |
| `docs/REPO_MAP.md` | Complete map of repo structure with key file descriptions |
| `docs/COPILOT_WORKFLOW.md` | Development workflow and PR best practices |
| `strategies/supply_demand_v1/README.md` | Complete S&D strategy specification (candles, zones, scoring, MTF, trade management) |

### Core Implementation Files

| File | Purpose |
|------|---------|
| `strategies/supply_demand_v1/strategy.py` | S&D strategy core logic (zone detection, scoring, trade planning) |
| `strategies/supply_demand_v1/runner.py` | Experiment runner and artifact generation |
| `scripts/run_supply_demand_v1.py` | CLI wrapper for running experiments |
| `experiments/sd_v1_default.yaml` | Default experiment config (5 symbols) |
| `experiments/sd_v1_wide_symbols.yaml` | Comprehensive experiment config (15 symbols) |

### Test Files

| File | Purpose |
|------|---------|
| `tests/test_supply_demand_zones.py` | Zone detection (DBR/RBD patterns, proximal/distal, freshness) |
| `tests/test_supply_demand_strategy.py` | Scoring, MTF gating, trade plan generation |
| `tests/test_supply_demand_mtf_gating.py` | Multi-timeframe gating rules (curve, trend, filtering) |
| `tests/test_supply_demand_fill_logic.py` | Order fills, TTL expiry, slippage/fees |
| `tests/test_supply_demand_integrity.py` | Integrity checks (look-ahead bias, R-multiple enforcement) |
| `tests/test_runner.py` | Experiment runner and artifact generation |

### Notebook Examples

| File | Purpose |
|------|---------|
| `notebooks/supply_demand/supply_demand_v1_backtest.ipynb` | S&D strategy demo (synthetic candles, no plots) |
| `notebooks/single-backtest/bitcoin-ma.ipynb` | Simple MA crossover strategy |
| `notebooks/single-backtest/matic-breakout.ipynb` | RSI + Bollinger Bands breakout |
| `notebooks/single-backtest/multipair-atr-breakout.ipynb` | Multi-pair ATR breakout |
| `notebooks/grid-search/multipair-breakout-grid-atr-slow.ipynb` | Grid search example |

### Setup and Configuration

| File | Purpose |
|------|---------|
| `pyproject.toml` | Poetry dependencies, Python version requirements |
| `Makefile` | Helper commands (`make trade-executor-clone`) |
| `run_notebooks.py` | Executes all notebooks except grid searches |

## Output Expectations for PRs

When finalizing a PR, provide the following in your PR description or final comment:

### 1. List Files Changed

```
Files created:
- strategies/supply_demand_v1/new_feature.py

Files modified:
- strategies/supply_demand_v1/strategy.py (added X, updated Y)
- tests/test_supply_demand_strategy.py (added test for X)
- strategies/supply_demand_v1/README.md (documented X)
```

### 2. Commands to Verify

Provide exact commands reviewers can run to validate your changes:

```bash
# Unit tests
poetry run pytest tests/test_supply_demand_strategy.py::test_new_feature -v

# Experiment run
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Check artifacts
cat artifacts/sd_v1/<timestamp>_<hash>/violations.json
```

### 3. Summary of Behavioral Impact

Explain what changed from a user perspective:

```
Before: Zones were scored only on freshness and leg-out strength
After: Zones now include profit zone distance in scoring (3 points max)

Impact on strategy:
- Total score increased from 0-7 to 0-10
- Setups near opposing zones now score higher
- Min setup score threshold remains 6.0
```

### 4. State Any Assumptions

If your implementation makes assumptions, state them explicitly:

```
Assumptions:
- HTF zones are always available (strategy skips decision cycles if missing)
- Candle data is pre-validated (open/high/low/close fields present)
- Position sizing uses fixed risk_pct (no dynamic adjustment)
```

## Copilot Prompt Patterns

To work efficiently with GitHub Copilot on this repo, follow these prompt patterns:

### Fast Context Loading

**DO:**
```
Read these exact files first:
1. docs/PROJECT_CONTEXT.md
2. docs/REPO_MAP.md
3. strategies/supply_demand_v1/README.md (sections: Zone Patterns, Scoring)

Then implement: [your task]
```

**DON'T:**
```
Help me understand this codebase and add a feature
```

**Why**: Loading specific files prevents re-exploration and gives precise context.

### Avoid Broad Exploration

**DO:**
```
Modify strategies/supply_demand_v1/strategy.py:
- Update score_odds_enhancers() to add profit zone scoring
- Add tests in tests/test_supply_demand_strategy.py
- Update README.md scoring section

Files to read: [list specific files]
```

**DON'T:**
```
Scan the repo and improve the scoring system
```

**Why**: Explicit file paths reduce token usage and prevent wandering.

### Clear Acceptance Criteria

**DO:**
```
Acceptance criteria:
✅ score_odds_enhancers() returns 0-10 (was 0-7)
✅ Profit zone adds 0/1.5/3 points based on available_R thresholds
✅ test_profit_zone_scoring() passes with 3 test cases
✅ README.md documents new scoring component
✅ Experiment run produces valid artifacts
```

**DON'T:**
```
Make the scoring better
```

**Why**: Concrete criteria prevent over-engineering and scope creep.

### Verification Commands

**DO:**
```
Commands to verify:
1. poetry run pytest tests/test_supply_demand_strategy.py::test_profit_zone_scoring -v
2. python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
3. Check violations.json has empty arrays
```

**DON'T:**
```
Test that it works
```

**Why**: Reviewers can copy-paste exact commands to validate changes.

### Example Full Prompt

```
Task: Add profit zone distance to odds enhancer scoring

Context files to read:
1. strategies/supply_demand_v1/README.md (section: Odds Enhancers)
2. strategies/supply_demand_v1/strategy.py (function: score_odds_enhancers)
3. tests/test_supply_demand_strategy.py (existing scoring tests)

Changes:
1. In strategy.py, add profit_zone_score calculation
2. Add test_profit_zone_scoring() with 3 cases (high/mid/low R)
3. Update README.md scoring section with new component

Do not:
- Refactor unrelated scoring components
- Change thresholds for existing components
- Modify zone detection logic

Acceptance criteria:
✅ score_odds_enhancers() returns 0-10 (was 0-7)
✅ Profit zone scoring: 3.0 (R>=3), 1.5 (R>=2), 0.0 (R<2)
✅ All tests pass: pytest tests/test_supply_demand_strategy.py -v
✅ Experiment generates valid artifacts

Commands to verify:
1. poetry run pytest tests/test_supply_demand_strategy.py -v
2. python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
```

## Key Technical Details

### Repository Structure

- **Scope**: Starter kit of trading strategy examples (mostly notebooks). Core S&D logic lives in `strategies/supply_demand_v1/strategy.py`; most notebooks consume that module.
- **Imports and paths**: Modules resolve via the package path `strategies.supply_demand_v1`. In notebooks we prepend the repo root to `sys.path`; in terminals run from repo root or set `PYTHONPATH=.` so imports work without relative hacks.

### Supply & Demand Strategy

- **Detection**: Uses DBR/RBD detection, freshness tracking, curve (HTF) and trend (ITF) classification, odds enhancer scoring, and trade plan building. 
- **Behavior assertions**: Tests are in `tests/test_supply_demand_zones.py` and `tests/test_supply_demand_strategy.py`.
- **Multi-timeframe signals**: `find_nearest_fresh_zones_htf` sets curve from fresh zones; `trend_direction_itf` uses pivot highs/lows via `detect_pivot_highs_lows`. Preserve these interfaces when extending features.

### Notebooks

- **Location**: Examples live under `notebooks/`. The S&D demo is `notebooks/supply_demand/supply_demand_v1_backtest.ipynb`; it generates synthetic candles and prints summaries (no plots).
- **Grid searches**: Should be skipped for automated runs.
- **Execution**: `run_notebooks.py` executes all notebooks except those containing `perform_grid_search`. `tests/test_notebooks.py` parametrizes `notebooks/single-backtest/*.ipynb` and honors `# @ts skip-test` / `# @ts skip-test-ci` pragmas in code cells.

### Dependencies & Setup

- **Poetry-managed**: Python >=3.11,<=3.12
- **trade-executor**: Expected as an editable dependency at `../trade-executor` (see `pyproject.toml`); helper: `make trade-executor-clone`. Some pins are unusual (e.g., `ipython < 8`).

### Testing

- **Command**: `poetry run pytest`
- **Focus**: Tests emphasize deterministic S&D logic—candle classification, zone detection, curve/trend analysis, scoring gates, 3R enforcement, and trade management.
- **Best practice**: Keep calculations deterministic and side-effect free where possible.

### Data Contracts

- **Candle dicts**: Require `open`, `high`, `low`, `close`
- **Zones**: Must carry proximal/distal, base/legout indices/lengths, freshness counts, and `legout_return`

### Trade Planning Rules

- **Entry**: At proximal
- **Stop**: Beyond distal with buffer
- **Minimum R**: Enforce `min_reward_risk` (default 3R) before returning a plan
- **Position size**: Uses `risk_pct`
- **Trade management**: `manage_trade_plan` moves stop to breakeven at `breakeven_at_r` and flags take-profit at `take_profit_at_r`

### CI/Backtests

- **Headless runs**: Prefer stdout summaries over interactive widgets
- **Grid searches**: Guard long grid searches with pragmas so they are skipped in automated runs

### Adding Strategies/Notebooks

- **Pattern**: Mirror the import pattern
- **Test first**: Add focused unit tests before relying on notebooks—the test suite is quicker than full notebook execution
