# Supply & Demand V1 - Upstream Compatibility Guide

## Overview

The Supply & Demand V1 strategy now supports **two execution paths**:

1. **CSV Backtest Adapter** (default) - For experiments, artifacts, and PR comparisons
2. **Upstream Adapter** (optional) - For integration with TradingStrategy.ai framework

This document explains the differences, when to use each, and how to get started with the upstream adapter.

---

## Architecture

```
Strategy Core (strategy_core.py)
  ├── Framework-agnostic logic
  ├── Zone detection (DBR/RBD patterns)
  ├── Freshness tracking
  ├── Multi-timeframe gating (HTF curve, ITF trend)
  ├── Scoring (odds enhancers)
  └── Trade planning (entry/stop/target calculations)
       ↓
       ├─────────────────────────────────┬─────────────────────────────────┐
       │                                 │                                 │
  CSV Backtest Adapter          Upstream Adapter                   Future Adapters
  (csv_backtest_adapter.py)     (decide_trades_adapter.py)         (e.g., live trading)
       │                                 │
       ├─ Fill simulation                ├─ PositionManager API
       ├─ TTL tracking                   ├─ Framework fills/TTL
       ├─ Position management            ├─ Framework positions
       ├─ PnL calculation                ├─ Framework PnL
       ├─ Parallel execution             └─ Upstream analytics
       └─ Artifact generation
```

---

## Feature Comparison

| Feature | CSV Adapter | Upstream Adapter | Notes |
|---------|-------------|------------------|-------|
| **Execution** |
| Zone detection | ✅ | ✅ | Same logic from strategy_core.py |
| MTF gating | ✅ | ✅ | Same logic from strategy_core.py |
| Scoring | ✅ | ✅ | Same logic from strategy_core.py |
| Trade planning | ✅ | ✅ | Same logic from strategy_core.py |
| Order fills | Manual simulation | Framework | Upstream uses built-in fill logic |
| TTL expiration | Manual tracking | Framework | Upstream handles automatically |
| Position tracking | Custom arrays | Framework | Upstream uses Portfolio state |
| PnL calculation | Manual | Framework | Upstream calculates automatically |
| **Data** |
| Synthetic candles | ✅ | ⚠️ Via config | CSV has built-in generator |
| Historical data | ✅ | ✅ | Both support real market data |
| Multi-timeframe | ✅ | ✅ | Both support HTF/ITF/LTF |
| **Execution Modes** |
| Spot trading | ✅ | ✅ | Both support long positions |
| Futures/Shorts | ✅ | ⚠️ Unconfirmed | CSV supports, upstream TBD |
| Parallel execution | ✅ | ❌ | CSV only (multi-symbol parallel) |
| **Artifacts** |
| summary.json | ✅ | ❌ | CSV only |
| trades.csv | ✅ | ❌ | CSV only |
| zones.csv | ✅ | ❌ | CSV only |
| orders.csv | ✅ | ❌ | CSV only |
| violations.json | ✅ | ❌ | CSV only (integrity checks) |
| decision_funnel.json | ✅ | ❌ | CSV only |
| **Analytics** |
| Equity curve | ✅ | ✅ | Both support |
| Win rate | ✅ | ✅ | Both calculate |
| R-multiples | ✅ | ✅ | Both calculate |
| Sharpe ratio | ⚠️ Basic | ✅ Advanced | Upstream has richer analytics |
| Max drawdown | ✅ | ✅ | Both calculate |
| Visualizations | ❌ | ✅ | Upstream has built-in charts |
| **Other** |
| Integrity checks | ✅ | ❌ | CSV validates look-ahead, R-calc |
| PR comparisons | ✅ | ⚠️ Manual | CSV generates artifacts for diffs |
| Community tools | ❌ | ✅ | Upstream integrates with ecosystem |

**Legend:**
- ✅ Fully supported
- ⚠️ Partially supported or unconfirmed
- ❌ Not supported

---

## When to Use Each Adapter

### Use CSV Adapter When:

✅ **Running experiments for PR validation**
- Need reproducible artifacts for before/after comparison
- Want to check integrity (look-ahead bias, R-multiple violations)
- Need parallel execution across multiple symbols

✅ **Debugging strategy logic**
- Want detailed CSV outputs for manual inspection
- Need per-symbol and per-zone breakdowns
- Want decision funnel metrics

✅ **Testing with synthetic data**
- Quick tests without downloading historical data
- Deterministic results with fixed seeds

✅ **Custom backtesting infrastructure**
- Need control over fill simulation
- Want to experiment with TTL or order logic
- Prefer CSV artifacts over framework-specific formats

### Use Upstream Adapter When:

✅ **Integrating with TradingStrategy.ai ecosystem**
- Want to use upstream analytics and visualizations
- Need to share strategies with community
- Want framework-maintained fill/position logic

✅ **Production trading (future)**
- When moving from backtest to live/paper trading
- When using upstream's execution infrastructure

✅ **Real market data**
- Want upstream's data APIs (Binance, DEX, etc.)
- Need historical data without manual downloads

✅ **Reduced maintenance**
- Don't want to maintain custom fill simulation
- Prefer framework's position tracking over custom logic

---

## Getting Started: CSV Adapter (Default)

The CSV adapter is the **default** and requires no additional setup.

### 1. Run an Experiment

```bash
# Run default experiment (5 symbols, synthetic data)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Run with parallel execution
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel
```

### 2. Check Artifacts

```bash
# Artifacts are written to ./artifacts/sd_v1/<timestamp>_<hash>/
ls artifacts/sd_v1/

# Inspect results
cat artifacts/sd_v1/<latest_folder>/summary.json
cat artifacts/sd_v1/<latest_folder>/violations.json
```

### 3. Compare Results Between PRs

```bash
# Run on main branch
git checkout main
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Note the folder: artifacts/sd_v1/20240101_120000_abc1234/

# Run on feature branch
git checkout feature/my-improvement
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Note the folder: artifacts/sd_v1/20240101_130000_def5678/

# Compare summary metrics
diff \
  artifacts/sd_v1/20240101_120000_abc1234/summary.json \
  artifacts/sd_v1/20240101_130000_def5678/summary.json
```

### 4. Programmatic Usage

```python
from strategies.supply_demand_v1.runner import run_backtest_experiment, write_artifacts, create_artifacts_folder

# Run experiment
result = run_backtest_experiment("experiments/sd_v1_default.yaml")

# Access metrics
print(f"Total trades: {result.aggregate_metrics['total_trades']}")
print(f"Win rate: {result.aggregate_metrics['overall_win_rate']:.2%}")

# Write artifacts
artifacts_dir = create_artifacts_folder()
write_artifacts(result, artifacts_dir)
```

---

## Getting Started: Upstream Adapter (Optional)

The upstream adapter requires **trade-executor** to be installed.

### 1. Install trade-executor

```bash
# Clone trade-executor to sibling directory (if not already cloned)
cd ..
git clone https://github.com/tradingstrategy-ai/trade-executor
cd trading-strategy-ai-getting-started

# Install dependencies with Poetry
poetry install

# Verify trade-executor is available
python -c "import tradeexecutor; print('✓ trade-executor installed')"
```

### 2. Create a Notebook

Create `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`:

```python
# Cell 1: Imports
from strategies.supply_demand_v1.decide_trades_adapter import decide_trades_sd_v1, create_indicators
from strategies.supply_demand_v1.strategy_core import SupplyDemandParameters
from tradeexecutor.backtest.backtest_runner import run_backtest_inline
from tradingstrategy.client import Client

# Cell 2: Parameters
class Parameters(SupplyDemandParameters):
    id = "supply_demand_v1"
    name = "Supply & Demand V1"
    # ... set other parameters

parameters = Parameters()

# Cell 3: Universe setup (TODO: Complete this)
# client = Client.create_live_client()
# strategy_universe = create_binance_universe(...)

# Cell 4: Run backtest
result = run_backtest_inline(
    name=parameters.name,
    engine_version="0.5",
    decide_trades=decide_trades_sd_v1,
    create_indicators=create_indicators,
    client=client,
    universe=strategy_universe,
    parameters=parameters,
    strategy_logging=False,
)

# Cell 5: Display results
state = result.state
trades = list(state.portfolio.get_all_trades())
print(f"Total trades: {len(trades)}")

# Use upstream analytics (equity curve, visualizations, etc.)
```

### 3. Current Limitations

⚠️ **The upstream adapter is currently a STUB** with NotImplementedError.

**TODO (Future PR):**
- Complete multi-timeframe candle extraction from strategy_universe
- Wire up zone detection, MTF analysis, scoring
- Test with real market data
- Validate that results match CSV adapter on same data

**For now, use the CSV adapter** for all backtesting needs.

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| **strategy_core.py** | ✅ Complete | Framework-agnostic logic extracted |
| **csv_backtest_adapter.py** | ✅ Complete | Refactored from runner.py |
| **runner.py** | ✅ Complete | Thin wrapper for backward compatibility |
| **decide_trades_adapter.py** | ⚠️ Stub | Guards imports, raises clear errors |
| **UPSTREAM_COMPATIBILITY.md** | ✅ Complete | This document |
| **README.md updates** | ⏳ Pending | Add compatibility section |
| **Tests** | ⏳ Pending | Regression tests for CSV adapter |
| **Example notebook** | ⏳ Pending | Upstream adapter example |

---

## Migration Path

### Phase 1: Current State (This PR)
- ✅ Strategy core extracted (strategy_core.py)
- ✅ CSV adapter refactored (csv_backtest_adapter.py)
- ✅ Backward compatibility maintained (runner.py)
- ✅ Upstream adapter stub created (decide_trades_adapter.py)
- ✅ Documentation added (this file)

### Phase 2: Complete Upstream Adapter (Future PR)
- ⏳ Implement decide_trades_sd_v1() fully
- ⏳ Test with synthetic data
- ⏳ Compare results with CSV adapter
- ⏳ Add example notebook
- ⏳ Document any behavioral differences

### Phase 3: Validate and Stabilize (Future PR)
- ⏳ Test with real market data (Binance futures)
- ⏳ Validate Sharpe, max DD, other metrics
- ⏳ Performance testing
- ⏳ Add unit tests for adapter logic

### Phase 4: Deprecation (If Upstream Mature)
- ⏳ If upstream adapter meets all needs, consider deprecating CSV adapter
- ⏳ OR keep CSV adapter as "experiments mode" long-term
- ⏳ Decision depends on community feedback and upstream features

---

## FAQ

### Q: Can I use both adapters in the same project?

**A:** Yes! They share the same strategy core logic (strategy_core.py) but use different execution paths. You can run experiments with the CSV adapter and integrate with upstream tools using the upstream adapter.

### Q: Will results be identical between adapters?

**A:** They should be very close, but not 100% identical due to:
- Different fill simulation logic
- Different slippage/fee models
- Different position tracking (may affect breakeven moves)

We will document any known differences once the upstream adapter is complete.

### Q: Why keep the CSV adapter if upstream is "better"?

**A:** The CSV adapter provides:
- Reproducible artifacts for PR comparisons
- Integrity checks (look-ahead bias, R-multiple validation)
- Parallel execution (faster for multi-symbol experiments)
- Decision funnel metrics (useful for debugging)

It's a valuable tool for development and testing, even if upstream is used for production.

### Q: Can I use the upstream adapter without trade-executor?

**A:** No. The upstream adapter requires trade-executor to be installed. If you only need CSV backtests, use `scripts/run_supply_demand_v1.py` which does NOT require trade-executor.

### Q: Does the upstream adapter support Binance futures?

**A:** Unknown at this time. The upstream examples focus on spot markets. We will test futures support in a future PR.

### Q: How do I report issues with the adapters?

**A:** File a GitHub issue with:
- Which adapter you're using (CSV or upstream)
- Config file used
- Expected vs. actual behavior
- Artifact files (if using CSV adapter)

---

## Related Documentation

- **strategies/supply_demand_v1/README.md** - Strategy specification
- **AUDIT_EXECUTIVE_SUMMARY.md** - Analysis of upstream framework
- **AUDIT_UPSTREAM_EXECUTION_FRAMEWORK.md** - Detailed upstream audit
- **notebooks/single-backtest/bitcoin-ma.ipynb** - Upstream adapter example (MA strategy)

---

## Summary

The Supply & Demand V1 strategy now supports **two execution paths**:

1. **CSV Adapter** (default) - Use for experiments, artifacts, PR comparisons
2. **Upstream Adapter** (optional) - Use for integration with TradingStrategy.ai framework

Both adapters share the same **strategy core logic** (zone detection, MTF gating, scoring) but differ in execution (fills, position tracking, PnL calculation).

**Current recommendation:** Use the CSV adapter for all backtesting needs. The upstream adapter is a stub and will be completed in a future PR.

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-04  
**Status:** Current
