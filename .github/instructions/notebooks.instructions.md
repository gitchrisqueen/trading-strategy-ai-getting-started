---
applyTo:
  - "notebooks/**/*.ipynb"
---

# Notebook Instructions

These instructions apply to all Jupyter notebooks under `notebooks/`.

## Keep Notebooks Thin - Call Into Modules

**Critical Rule**: Notebooks are for demonstration and exploration, not for housing core logic.

### Why Notebooks Should Be Thin

- **Maintainability**: Logic in notebooks is hard to test and refactor
- **Reusability**: Code in notebooks can't be imported by other notebooks or scripts
- **Testing**: Notebook cells can't be unit tested effectively
- **Version control**: Notebooks generate noisy diffs that are hard to review
- **Performance**: Repeated notebook runs shouldn't duplicate heavy computation

### Good Notebook Structure

```python
# Cell 1: Imports (call into modules)
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))  # Add repo root to path

from strategies.supply_demand_v1.strategy import (
    detect_supply_demand_zones,
    score_odds_enhancers,
    build_trade_plan,
)

# Cell 2: Parameters at top (user configuration)
class Parameters:
    symbols = ['BTC/USDT', 'ETH/USDT']
    start_date = '2023-01-01'
    end_date = '2023-12-31'
    initial_capital = 10_000
    risk_pct = 0.02
    min_setup_score = 6.0

# Cell 3: Data loading (lightweight)
candles = load_candles(Parameters.symbols, Parameters.start_date, Parameters.end_date)

# Cell 4: Strategy execution (calls modules)
zones = detect_supply_demand_zones(candles, min_base_candles=1, max_base_candles=6)
scored_zones = [score_odds_enhancers(z, opposing_zone=None, params=Parameters) for z in zones]
trade_plans = [build_trade_plan(z, opposing_zone=None, account_size=Parameters.initial_capital, params=Parameters) 
               for z in scored_zones if z['score'] >= Parameters.min_setup_score]

# Cell 5: Results visualization (notebook-appropriate)
print(f"Detected {len(zones)} zones")
print(f"Tradeable setups: {len(trade_plans)}")
```

### Bad Notebook Structure (DON'T DO THIS)

```python
# Cell 1: Giant function definitions (BAD!)
def detect_zones(candles):
    # 200 lines of zone detection logic
    # This should be in strategies/supply_demand_v1/strategy.py
    pass

def score_zones(zones):
    # 150 lines of scoring logic
    # This should be in strategies/supply_demand_v1/strategy.py
    pass

# Cell 2: Inline calculations (BAD!)
zones = []
for i in range(len(candles)):
    # 50 lines of pattern matching logic
    # This duplicates module code or should be moved to modules
    pass
```

## Parameter Cell at Top

**Every notebook should have a clear "Parameters" or "Configuration" cell near the top.**

### Why Parameters at Top?

- **User-friendly**: Users can modify behavior without reading entire notebook
- **Reproducibility**: Easy to see what settings were used for a run
- **Documentation**: Self-documenting what is configurable
- **Testing**: Easy to run with different parameters for testing

### Example Parameter Cell

```python
# ============================================================
# PARAMETERS - Modify these to customize the backtest
# ============================================================

class Parameters:
    """Configuration for Supply & Demand V1 backtest"""
    
    # Trading universe
    symbols = ['BTC/USDT', 'ETH/USDT', 'MATIC/USDT']
    
    # Date range
    start_date = '2023-01-01'
    end_date = '2023-12-31'
    
    # Capital
    initial_capital = 10_000
    risk_pct = 0.02  # Risk 2% per trade
    
    # Strategy parameters
    min_setup_score = 6.0
    min_reward_risk = 3.0
    breakeven_at_r = 2.0
    take_profit_at_r = 3.0
    
    # Zone detection
    min_base_candles = 1
    max_base_candles = 6
    proximal_mode = 'body'
    
    # Multi-timeframe
    htf_tf = '4h'
    itf_tf = '1h'
    ltf_tf = '15m'
    
    # Costs
    fees_bps = 10.0  # 0.1%
    slippage_bps = 5.0  # 0.05%
```

### Parameter Cell Best Practices

- **Use a class or dict**: Group related parameters
- **Add comments**: Explain what each parameter does
- **Include units**: Specify percentages, timeframes, etc.
- **Set reasonable defaults**: Notebook should work out-of-the-box
- **Separate concerns**: Group parameters by category (data, strategy, costs)

## Never Embed Large Logic That Duplicates Modules

**If logic exists in a module, import it. Don't copy-paste or reimplement.**

### Why Duplication Is Bad

- **Maintenance burden**: Bugs must be fixed in multiple places
- **Inconsistency**: Notebook and module behavior can diverge
- **Testing**: Module code is tested, notebook code is not
- **Confusion**: Which version is "correct"?

### Examples of Duplication to Avoid

#### ❌ DON'T: Copy-paste zone detection

```python
# Cell: Zone detection (BAD - duplicates strategy.py)
zones = []
for i in range(len(candles) - 3):
    # 50 lines of DBR/RBD pattern matching
    # This is copy-pasted from strategy.py
    pass
```

#### ✅ DO: Import zone detection

```python
# Cell: Zone detection (GOOD - calls module)
from strategies.supply_demand_v1.strategy import detect_supply_demand_zones

zones = detect_supply_demand_zones(candles, min_base_candles=1, max_base_candles=6)
```

#### ❌ DON'T: Reimplement scoring

```python
# Cell: Scoring (BAD - reimplements scoring logic)
for zone in zones:
    score = 0
    if zone['freshness_touches'] == 0:
        score += 3
    # ... 40 more lines
    zone['score'] = score
```

#### ✅ DO: Import scoring

```python
# Cell: Scoring (GOOD - calls module)
from strategies.supply_demand_v1.strategy import score_odds_enhancers

scored_zones = [score_odds_enhancers(z, opposing_zone=None, params=Parameters) for z in zones]
```

## Notebook-Specific Logic (What Belongs in Notebooks)

Some logic is appropriate in notebooks:

### ✅ Visualization and Plotting

```python
import matplotlib.pyplot as plt

# Plot equity curve
plt.figure(figsize=(12, 6))
plt.plot(equity_curve)
plt.title('Equity Curve')
plt.xlabel('Trade Number')
plt.ylabel('Account Value ($)')
plt.grid(True)
plt.show()
```

### ✅ Interactive Exploration

```python
# Interactive widgets for parameter exploration
from ipywidgets import interact

@interact(min_score=(0, 10, 0.5))
def explore_score_threshold(min_score):
    filtered_zones = [z for z in scored_zones if z['score'] >= min_score]
    print(f"Zones above score {min_score}: {len(filtered_zones)}")
```

### ✅ Formatted Output

```python
# Pretty-print results
from tabulate import tabulate

print("\nTop 10 Zones by Score:")
print(tabulate(
    [[z['zone_type'], z['proximal'], z['distal'], z['score']] for z in top_zones],
    headers=['Type', 'Proximal', 'Distal', 'Score'],
    tablefmt='grid'
))
```

### ✅ Ad-hoc Analysis

```python
# Quick statistical analysis
print(f"Average zone score: {np.mean([z['score'] for z in zones]):.2f}")
print(f"Zones with score >= 8: {sum(1 for z in zones if z['score'] >= 8)}")
print(f"Fresh zones: {sum(1 for z in zones if z['is_fresh'])}")
```

## Notebook Organization Template

Use this structure for new notebooks:

```python
# Cell 1: Title and Description
"""
# Supply & Demand V1 Backtest

This notebook demonstrates the Supply & Demand V1 trading strategy:
- Detects DBR/RBD zones on 15m timeframe
- Uses HTF (4h) for curve analysis and ITF (1h) for trend
- Scores setups using odds enhancers
- Enforces 3R minimum reward-to-risk ratio

**Data**: Synthetic candles (for reproducibility)
**Symbols**: BTC/USDT, ETH/USDT
**Date Range**: 2023-01-01 to 2023-12-31
"""

# Cell 2: Imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))

import pandas as pd
import numpy as np

from strategies.supply_demand_v1.strategy import (
    detect_supply_demand_zones,
    score_odds_enhancers,
    build_trade_plan,
    manage_trade_plan,
)

# Cell 3: Parameters
class Parameters:
    # ... parameter definitions

# Cell 4: Data Loading
candles = load_or_generate_candles(Parameters)

# Cell 5: Strategy Execution
zones = detect_supply_demand_zones(...)
scored_zones = [score_odds_enhancers(...) for z in zones]
trade_plans = [build_trade_plan(...) for z in scored_zones]

# Cell 6: Results Summary
print(f"Zones detected: {len(zones)}")
print(f"Tradeable setups: {len(trade_plans)}")
# ... more summary stats

# Cell 7: Detailed Analysis (optional)
# Zone distribution, score breakdown, etc.

# Cell 8: Visualization (optional)
# Charts, plots, tables

# Cell 9: Conclusions (optional)
"""
## Key Findings

- Detection rate: X zones per 100 candles
- Average setup score: Y
- Demand vs. Supply ratio: Z
"""
```

## Running Notebooks

### From Jupyter Interface

1. Start Jupyter: `poetry shell && jupyter notebook`
2. Navigate to notebook file
3. Select kernel (Python 3.11 or 3.12)
4. Run cells: `Cell → Run All` or `Shift+Enter` per cell

### From Command Line

```bash
# Run single notebook
poetry run jupyter nbconvert --to notebook --execute notebooks/supply_demand/supply_demand_v1_backtest.ipynb

# Run all notebooks (uses run_notebooks.py)
python run_notebooks.py
```

### From Tests

```bash
# Run notebook tests (parameterized)
poetry run pytest tests/test_notebooks.py -v
```

## Notebook Testing Pragmas

Use pragmas to control automated testing:

### Skip Notebook in All Tests

Add this pragma to a code cell:

```python
# @ts skip-test
# This notebook is skipped in automated tests
```

### Skip Notebook in CI Only

Add this pragma to a code cell:

```python
# @ts skip-test-ci
# This notebook runs locally but is skipped in CI
```

### When to Use Skip Pragmas

- **Long-running notebooks**: Grid searches, large backtests (use `skip-test-ci`)
- **Interactive notebooks**: Require user input or manual intervention (use `skip-test`)
- **Experimental notebooks**: Work-in-progress, not ready for testing (use `skip-test`)
- **Visualization-heavy notebooks**: Require display, not suitable for headless testing (use `skip-test-ci`)

### Example

```python
# Cell 1: Parameters
# @ts skip-test-ci
# This grid search takes 30 minutes and is skipped in CI

class Parameters:
    # Grid search ranges
    min_scores = [5.0, 6.0, 7.0, 8.0]
    min_r_values = [2.0, 2.5, 3.0, 3.5]
    # ... more parameters
```

## Notebook Output Expectations

### For Example Notebooks (single-backtest/)

- **Execution time**: < 2 minutes per notebook
- **Output**: Summary statistics, key metrics (no need for plots in automated runs)
- **Errors**: Should run without errors in headless mode

### For Grid Search Notebooks (grid-search/)

- **Execution time**: 10+ minutes (skip in CI with pragma)
- **Output**: Parameter combinations, performance grid, best parameters
- **Errors**: Expected to be skipped in automated tests

### For Supply & Demand Notebooks (supply_demand/)

- **Execution time**: ~1 minute
- **Output**: Zone detection stats, trade plan summary, performance metrics
- **Errors**: Should run without errors (uses synthetic data for reproducibility)

## Common Notebook Anti-Patterns to Avoid

### ❌ Importing from Relative Paths

**DON'T:**
```python
import sys
sys.path.append('../../strategies/supply_demand_v1')  # Fragile
from strategy import detect_zones
```

**DO:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))  # Repo root
from strategies.supply_demand_v1.strategy import detect_supply_demand_zones
```

### ❌ Hardcoded Paths

**DON'T:**
```python
data = pd.read_csv('/Users/bob/projects/trading/data/btc.csv')  # Won't work for others
```

**DO:**
```python
from pathlib import Path
data_dir = Path.cwd().parent / 'data'
data = pd.read_csv(data_dir / 'btc.csv')
```

### ❌ Notebooks That Modify System State

**DON'T:**
```python
import os
os.chdir('/some/other/directory')  # Breaks subsequent cells
```

**DO:**
```python
from pathlib import Path
data_path = Path('/some/other/directory') / 'data.csv'  # Use paths, don't chdir
```

### ❌ Cells That Depend on Run Order

**DON'T:**
```python
# Cell 5
result = process_data(data)

# Cell 7 (depends on Cell 5, but skips Cell 6)
final = transform(result)  # Fails if Cell 5 not run
```

**DO:**
```python
# Each cell should be runnable if prerequisites are met
# Use "Run All" to ensure consistent execution
```

### ❌ Printing Excessive Output

**DON'T:**
```python
for i in range(10_000):
    print(f"Processing candle {i}")  # Clogs notebook output
```

**DO:**
```python
print(f"Processing {len(candles)} candles...")
# Use progress bars or summary stats instead
```

## Notebook Performance Tips

- **Cache expensive computations**: Save intermediate results to disk
- **Use synthetic data for demos**: Faster than downloading real data
- **Limit data size**: Use date ranges or symbol counts appropriate for notebook execution time
- **Avoid recomputing**: If a cell takes >10 seconds, cache the result

### Example: Caching

```python
# Cell: Data loading with cache
from pathlib import Path
import pickle

cache_file = Path('/tmp/candles_cache.pkl')

if cache_file.exists():
    print("Loading candles from cache...")
    with open(cache_file, 'rb') as f:
        candles = pickle.load(f)
else:
    print("Downloading candles...")
    candles = download_candles(symbols, start_date, end_date)
    with open(cache_file, 'wb') as f:
        pickle.dump(candles, f)
```

## Documentation in Notebooks

### Use Markdown Cells Liberally

- **Section headers**: Use `#`, `##`, `###` for hierarchy
- **Explanatory text**: Explain what each section does
- **Inline code**: Use backticks for variable names and functions
- **Links**: Reference external docs and related notebooks

### Example Markdown Cell

```markdown
## Zone Detection

This section detects **Drop-Base-Rally** (demand) and **Rally-Base-Drop** (supply) zones using the following criteria:

- **Base length**: 1-6 candles
- **Boring candle**: Body ≤ 50% of range
- **Exciting candle**: Body > 50% of range

See [Supply & Demand V1 README](../../strategies/supply_demand_v1/README.md) for full specification.
```

## Notebook Quality Checklist

Before committing a notebook:

- [ ] Parameter cell is at the top and clearly labeled
- [ ] Notebook imports from modules, doesn't duplicate logic
- [ ] Notebook runs "Cell → Run All" without errors
- [ ] Execution time is reasonable (< 2 minutes, or has skip pragma)
- [ ] Output is clean (no excessive print statements)
- [ ] Markdown cells explain what each section does
- [ ] Paths are relative or use `Path` objects (no hardcoded absolute paths)
- [ ] Code follows repo conventions (imports, naming, style)
- [ ] Skip pragmas added if notebook is slow or interactive
