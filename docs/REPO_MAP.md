# Repository Map

## Start Here

### For Learning the Supply & Demand V1 Strategy

1. **Notebook**: `notebooks/supply_demand_v1_backtest.ipynb`
   - Interactive demo of the S&D strategy with synthetic data
   - Shows zone detection, scoring, trade generation, and performance metrics

2. **Strategy Code**: `strategies/supply_demand_v1/strategy.py`
   - Core implementation of all S&D logic
   - Contains all functions for zone detection, scoring, and trade planning

3. **Strategy Spec**: `strategies/supply_demand_v1/TradingStrategySpec.md`
   - Complete text-only specification
   - Defines rules, formulas, and decision logic

### For General Strategy Development

1. **Main README**: `README.md`
   - Repository overview, setup instructions, example strategies
   
2. **Example Notebooks**: `notebooks/single-backtest/`
   - Various strategy examples (MA crossover, ATR breakout, portfolio construction)

## Root Directory

```
├── README.md                      Main repository documentation
├── pyproject.toml                Poetry dependencies and project metadata
├── poetry.lock                    Locked dependency versions
├── Makefile                       Helper commands (e.g., make trade-executor-clone)
├── .env.example                   Template for environment variables
├── .gitignore                     Git ignore patterns
├── run_notebooks.py               Script to execute all notebooks automatically
├── SUMMARY.md                     High-level project summary
├── IMPLEMENTATION_COMPLETE.md     Supply & Demand V1 completion report
├── MTF_IMPLEMENTATION_SUMMARY.md  Multi-timeframe gating feature summary
└── splash.png                     Repository splash image
```

## Key Folders

### `/notebooks/`

Contains Jupyter notebooks demonstrating backtests and research.

**Structure**:
```
notebooks/
├── supply_demand_v1_backtest.ipynb  ← Supply & Demand V1 strategy demo
├── supply_demand_v1_backtest.html   HTML export of notebook
├── single-backtest/                 Single-strategy backtest examples
│   ├── bitcoin-ma.ipynb             Simple MA crossover (BTC)
│   ├── eth-10-days-high.ipynb       Rolling maximum strategy
│   ├── moving-average.ipynb         Fast/slow EMA crossover
│   ├── matic-breakout.ipynb         RSI + Bollinger Bands breakout
│   ├── bitcoin-atr-breakout.ipynb   ATR-based breakout with regime filter
│   ├── multipair-atr-breakout.ipynb Multiple pairs ATR breakout
│   ├── portfolio-construction.ipynb Portfolio rebalancing example
│   ├── momentum-basket.ipynb        Open-ended momentum basket
│   └── ...                          Additional examples
├── grid-search/                     Parameter optimization examples
│   ├── multipair-atr-breakout-slow.ipynb  Grid search demo
│   └── btc-bb-1h-binance-optimiser.ipynb  Gaussian Process optimiser
├── research/                        Research-only notebooks
│   ├── regime-filter-playground.ipynb     ADX regime filter testing
│   └── regime-filter-optimise.ipynb       Regime filter optimization
└── liquidity-provision/             Liquidity provision examples
```

**Key file**: `supply_demand_v1_backtest.ipynb`
- Demonstrates full Supply & Demand V1 backtest
- Generates synthetic candle data with embedded S&D patterns
- Runs zone detection, scoring, trade simulation
- Outputs performance metrics and integrity report

### `/strategies/`

Contains strategy implementations as Python modules.

```
strategies/
└── supply_demand_v1/                   Supply & Demand V1 strategy package
    ├── strategy.py                     Core strategy implementation
    ├── integrity.py                    Backtest integrity validation
    ├── demo_zone_detection.py          Demo script for zone detection
    ├── __init__.py                     Package initializer
    ├── README.md                       Strategy README
    ├── TradingStrategySpec.md          Complete text-only specification
    ├── IMPLEMENTATION.md               Implementation notes
    ├── IMPLEMENTATION_COMPLETE.md      Completion report
    ├── MTF_GATING_GUIDE.md            Multi-timeframe gating guide
    ├── REALISTIC_FILL_LOGIC.md        Realistic limit order fill logic
    └── INTEGRITY_REPORT.md             Integrity checks documentation
```

**Key file**: `strategies/supply_demand_v1/strategy.py` (1000+ lines)
- `SupplyDemandParameters`: Configuration dataclass
- Zone detection: `detect_zones_dbr_rbd()`, `compute_zone_lines_proximal_distal()`
- Candle analysis: `identify_boring_candles()`, `identify_exciting_candles()`
- Multi-timeframe: `find_nearest_fresh_zones_htf()`, `curve_location()`, `trend_direction_itf()`
- Scoring: `odds_enhancer_score()`
- Trade planning: `build_trade_plan()`, `manage_trade_plan()`
- Position sizing: `calculate_position_size()`

### `/tests/`

Contains pytest test suites for all strategies.

```
tests/
├── test_supply_demand_zones.py       Zone detection and classification tests
├── test_supply_demand_strategy.py    Strategy behavior and scoring tests
├── test_supply_demand_integrity.py   Backtest integrity validation tests
├── test_supply_demand_mtf_gating.py  Multi-timeframe gating tests
├── test_supply_demand_fill_logic.py  Realistic fill logic tests
└── test_notebooks.py                 Notebook execution tests (parametrized)
```

**Key tests**:
- `test_supply_demand_zones.py`: Tests boring/exciting classification, DBR/RBD detection, proximal/distal calculation
- `test_supply_demand_strategy.py`: Tests scoring, trade planning, position sizing, trade management
- `test_supply_demand_integrity.py`: Tests look-ahead bias, R-multiple accuracy, entry timing
- `test_notebooks.py`: Parametrized tests that execute notebooks in `notebooks/single-backtest/`

Run tests:
```bash
poetry run pytest                    # All tests
poetry run pytest tests/test_supply_demand_zones.py  # Specific file
poetry run pytest -v                 # Verbose output
```

### `/docs/`

Documentation for the repository.

```
docs/
├── PROJECT_CONTEXT.md                  ← You are reading related docs
├── REPO_MAP.md                         This file
├── STRATEGY_SUPPLY_DEMAND_V1.md        Complete S&D strategy specification
├── COPILOT_WORKFLOW.md                 Development workflow for future PRs
└── TradingStrategySpec.md              Original trading strategy spec
```

### `/scripts/`

Utility scripts for data export and research.

```
scripts/
└── uniswap-trading-universe/
    ├── 01-export-csv-uniswap-v2-v3-ethereum-top-100.py
    ├── 02-export-csv-uniswap-v2-v3-ethereum-top-100-sniffed.py
    └── 03-export-csv-uniswap-v2-v3-ethereum-top-100-sniffed-agg.py
```

Purpose: Export OHLCV data from Uniswap for use in external tools (RealTest, MetaTrader)

### `/examples/`

Example standalone scripts demonstrating specific features.

```
examples/
└── realistic_fill_logic_demo.py    Demonstrates realistic limit order fills
```

### `/.devcontainer/`

Dev container configuration for GitHub Codespaces and VS Code.

```
.devcontainer/
├── devcontainer.json    Container configuration
└── README.md            Dev container setup notes
```

### `/.github/`

GitHub configuration and CI workflows.

```
.github/
├── copilot-instructions.md    Instructions for GitHub Copilot
└── workflows/                 CI/CD workflows (if present)
```

### `/getting_started/`

Helper modules for getting started (minimal usage in current examples).

### `/data/`

Data directory for cached market data (created at runtime).

### `/scratchpad/`

Temporary workspace for experiments and development.

## Import Patterns

### In Notebooks

Notebooks use this pattern to import strategy modules:

```python
import sys
import os

# Add repository root to path
repo_root = os.path.abspath("..")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import from packaged path
from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    detect_zones_dbr_rbd,
    # ... other imports
)
```

### In Tests

Tests import directly using the package path:

```python
from strategies.supply_demand_v1.strategy import (
    identify_boring_candles,
    detect_zones_dbr_rbd,
    SupplyDemandParameters,
)
```

### In Terminals

Run from repository root with:

```bash
PYTHONPATH=. python scripts/your_script.py
```

Or activate poetry shell:

```bash
poetry shell
python scripts/your_script.py
```

## Configuration Files

### `pyproject.toml`

Poetry configuration with:
- Python version: `>=3.11,<=3.12`
- Main dependency: `trade-executor` (editable from `../trade-executor`)
- Key packages: `pandas`, `numpy`, `plotly`, `jupyter`, `ipython<8`
- Test dependencies: `pytest`, `nbformat`, `nbconvert`

### `poetry.lock`

Locked versions for reproducible builds.

### `.gitignore`

Ignores:
- Python bytecode (`__pycache__/`, `*.pyc`)
- Virtual environments
- Jupyter checkpoints (`.ipynb_checkpoints/`)
- Data cache files
- IDE settings

## Special Files

### `run_notebooks.py`

Executes all notebooks in `notebooks/` directory:
- Skips grid-search notebooks (checks for `perform_grid_search`)
- Used for automated validation

### `Makefile`

Helper commands:
```bash
make trade-executor-clone    # Clone trade-executor to ../trade-executor
```

## Notes for Developers

1. **Module resolution**: The repo uses packaged imports (`strategies.supply_demand_v1`) not relative imports
2. **Path setup**: Notebooks add repo root to `sys.path` for module resolution
3. **Testing**: Tests are comprehensive and deterministic (no randomness in core logic)
4. **Documentation**: Each strategy has a README and spec in its directory
5. **Notebook pragmas**: Use `# @ts skip-test` or `# @ts skip-test-ci` in notebook cells to skip automated testing
