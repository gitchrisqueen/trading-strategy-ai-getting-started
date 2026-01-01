# Project Context

## What This Repository Is For

This repository is a **getting started kit for algorithmic trading** with [Trading Strategy SDK](https://tradingstrategy.ai). It provides:

- **Example backtesting notebooks** for various trading strategies
- **Strategy development framework** using Jupyter notebooks and Python
- **Market data integration** for both DEX (decentralized exchanges) and CEX (centralized exchanges like Binance)
- **Live trade execution capabilities** through smart contract vaults
- **Supply & Demand V1 strategy** - A complete, production-ready zone-based trading strategy

The repository is designed to help traders and developers:
1. Learn algorithmic trading concepts
2. Backtest strategies on real market data
3. Develop custom trading strategies
4. Deploy strategies for live trading

## How to Set Up the Environment

### Prerequisites

- **Python**: Version >=3.11, <=3.12
- **Poetry**: For dependency management
- **Git**: For cloning the repository and submodules

### Option 1: GitHub Codespaces (Easiest)

1. Click **Create codespace on master** on the [GitHub repository page](https://github.com/tradingstrategy-ai/getting-started)
2. Wait for the environment to launch (1-2 minutes)
3. Open a notebook from `notebooks/` directory
4. Select Python kernel: `/usr/local/bin/python`
5. Run cells

### Option 2: Local Setup with Poetry

```bash
# Clone repository with submodules
git clone --recursive https://github.com/tradingstrategy-ai/getting-started.git
cd getting-started

# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Start Jupyter
jupyter notebook
```

### Option 3: Using trade-executor as Editable Dependency

The repository expects `trade-executor` as an editable dependency at `../trade-executor`:

```bash
# Clone trade-executor alongside this repo
make trade-executor-clone

# Or manually:
git clone https://github.com/tradingstrategy-ai/trade-executor.git ../trade-executor
```

## Running the Supply & Demand V1 Strategy

### Notebook Location

**Primary notebook**: `notebooks/supply_demand/supply_demand_v1_backtest.ipynb`

### Quick Start

1. **Start Jupyter**:
   ```bash
   poetry shell
   jupyter notebook
   ```

2. **Open the notebook**: Navigate to `notebooks/supply_demand/supply_demand_v1_backtest.ipynb`

3. **Configure parameters** in the "Parameters Configuration" cell:
   - Trading pairs (default: `BTC/USDT`, `ETH/USDT`)
   - Date range for backtest
   - Initial capital
   - Strategy parameters (risk %, scoring thresholds, etc.)

4. **Run all cells**: `Cell → Run All`

5. **View results**:
   - Zone detection statistics
   - Multi-timeframe gating analysis
   - Trade execution summary
   - Performance metrics (win rate, R-multiples, drawdown)
   - Trade-by-trade details

### Expected Output

The notebook generates:
- **Zone Detection**: Identifies DBR (demand) and RBD (supply) zones
- **Scoring**: Applies odds enhancers (freshness, leg-out strength, base length)
- **Trade Plans**: Entry/stop/target for each setup
- **Performance Summary**:
  ```
  BACKTEST RESULTS SUMMARY
  Initial Capital:    $10,000.00
  Final Equity:       $11,400.00
  Total Return:       14.00%
  Win Rate:           60.0%
  Average R:          1.40R
  Max Drawdown:       -3.57%
  ```

### Customization

Edit these parameters in the first code cell:

- `min_setup_score`: Filter trade quality (higher = more selective)
- `risk_pct`: Position sizing (default 2%)
- `boring_body_ratio` / `exciting_body_ratio`: Candle classification thresholds
- `min_reward_risk`: Minimum R:R ratio (default 3:1)
- `breakeven_at_r`: When to move stop to breakeven (default 2R)
- `take_profit_at_r`: When to close position (default 3R)

## Where the Strategy Implementation Lives

### Core Strategy Module

**Path**: `strategies/supply_demand_v1/strategy.py`

This module contains:
- **Parameters**: `SupplyDemandParameters` dataclass with all configurable parameters
- **Data structures**: `Zone`, `TradePlan`, enums for `ZoneType`, `CurveLocation`, `TrendDirection`
- **Candle analysis**: `identify_boring_candles()`, `identify_exciting_candles()`
- **Zone detection**: `detect_zones_dbr_rbd()` for DBR and RBD pattern detection
- **Proximal/distal calculation**: `compute_zone_lines_proximal_distal()`
- **Freshness tracking**: `is_zone_fresh()` to track zone retest status
- **Multi-timeframe analysis**:
  - `find_nearest_fresh_zones_htf()` - Finds HTF supply/demand zones
  - `curve_location()` - Determines if price is HIGH, LOW, or EQUILIBRIUM
  - `trend_direction_itf()` - Classifies trend as UP, DOWN, or SIDEWAYS
- **Scoring**: `odds_enhancer_score()` - Applies odds enhancers to rate setup quality
- **Trade planning**: `build_trade_plan()` - Generates entry/stop/target with position sizing
- **Trade management**: `manage_trade_plan()` - Handles breakeven and profit-taking

### Supporting Modules

**Path**: `strategies/supply_demand_v1/integrity.py`

Quality control module:
- `run_integrity_checks()` - Validates backtest integrity
- `print_integrity_report()` - Generates human-readable integrity report

Checks for:
- Look-ahead bias (decision before zone creation)
- Entry before zone creation
- R-multiple calculation accuracy
- Minimum R enforcement

## Where Outputs/Reports Are Generated

### Notebook Output

The `supply_demand_v1_backtest.ipynb` notebook generates:

1. **Console output** (appears in notebook cells):
   - Zone detection statistics
   - Multi-timeframe gating statistics
   - Trade execution count
   - Performance summary

2. **HTML export** (if saved):
   - `notebooks/supply_demand/supply_demand_v1_backtest.html`

### Test Reports

Run tests with:
```bash
poetry run pytest
```

Test coverage includes:
- `tests/test_supply_demand_zones.py` - Zone detection logic
- `tests/test_supply_demand_strategy.py` - Strategy behavior
- `tests/test_supply_demand_integrity.py` - Backtest integrity
- `tests/test_supply_demand_mtf_gating.py` - Multi-timeframe filtering
- `tests/test_supply_demand_fill_logic.py` - Realistic order fills

### Automated Notebook Execution

Run all notebooks:
```bash
python run_notebooks.py
```

This script:
- Executes all notebooks in `notebooks/single-backtest/`
- Skips grid-search notebooks (marked with `perform_grid_search`)
- Honors test skip pragmas: `# @ts skip-test`, `# @ts skip-test-ci`

## Key Dependencies

- **trade-executor**: Core trading framework (editable install from `../trade-executor`)
- **pandas**: Data manipulation
- **numpy**: Numerical computations
- **jupyter/ipython**: Notebook environment (ipython pinned to <8)
- **plotly**: Interactive visualizations (>6)
- **pytest**: Testing framework

## Environment Variables

Create `.env` from `.env.example` if needed for:
- API keys for data providers
- Configuration for live trading (not used in backtests)

## Common Issues and Solutions

### Import Errors

If you see `ModuleNotFoundError: No module named 'strategies'`:

1. Run the first cell in the notebook to clear cached modules
2. Restart the kernel
3. Ensure `sys.path` includes repo root

The notebook adds the repo root to path automatically:
```python
import sys, os
repo_root = os.path.abspath("..")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
```

### Trade Executor Missing

If you see errors about `trade-executor`:

```bash
# Clone trade-executor
make trade-executor-clone

# Or manually
git clone https://github.com/tradingstrategy-ai/trade-executor.git ../trade-executor
poetry install
```

### Slow Performance on Mac M1/M2

The Docker image is built for Intel. Local Poetry installation is faster on Apple Silicon.

## Next Steps

1. **Explore other examples**: Check `notebooks/single-backtest/` for more strategies
2. **Read strategy docs**: See `strategies/supply_demand_v1/README.md` for complete strategy spec
3. **Review repository map**: See `docs/REPO_MAP.md` for file structure
4. **Learn workflow**: See `docs/COPILOT_WORKFLOW.md` for development guidelines
5. **Run tests**: Verify your environment with `poetry run pytest`
6. **Customize parameters**: Experiment with different parameter combinations
7. **Try live trading**: Follow [live trade executor example](https://github.com/tradingstrategy-ai/dex-live-algorithmic-trading-example)
