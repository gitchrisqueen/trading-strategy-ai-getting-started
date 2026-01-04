# Upstream Framework Audit - Document Navigation

**Audit Date**: 2026-01-03  
**Purpose**: Compare upstream TradingStrategy.ai execution framework with our custom Supply & Demand V1 implementation

---

## Quick Start: Which Document Should I Read?

### For Executives / Decision Makers
👉 **Start here**: [AUDIT_EXECUTIVE_SUMMARY.md](AUDIT_EXECUTIVE_SUMMARY.md)

**What's in it**:
- ✅ Findings in bullet format (quick scan)
- ✅ Upstream patterns with exact file paths
- ✅ Our code overlap with line numbers
- ✅ Recommendation for next PR (file-by-file plan)

**Read time**: 10-15 minutes

---

### For Technical Implementation
👉 **Start here**: [UPSTREAM_AUDIT_FINDINGS.md](UPSTREAM_AUDIT_FINDINGS.md)

**What's in it**:
- ✅ Structured findings (upstream vs custom)
- ✅ Complete overlap analysis (what we re-implemented)
- ✅ Next PR outline with phases
- ✅ Compatibility layer architecture
- ✅ File-by-file changes list

**Read time**: 15-20 minutes

---

### For Deep Dive / Architecture Review
👉 **Start here**: [AUDIT_UPSTREAM_EXECUTION_FRAMEWORK.md](AUDIT_UPSTREAM_EXECUTION_FRAMEWORK.md)

**What's in it**:
- ✅ Complete upstream framework analysis
- ✅ Detailed custom implementation breakdown
- ✅ Function-by-function overlap comparison
- ✅ Binance futures support analysis
- ✅ Risk analysis and decision matrix
- ✅ Migration path with phases

**Read time**: 30-40 minutes

---

## Document Comparison

| Document | Size | Audience | Focus |
|----------|------|----------|-------|
| **AUDIT_EXECUTIVE_SUMMARY.md** | 19KB | Leadership, PMs | Findings + Recommendations |
| **UPSTREAM_AUDIT_FINDINGS.md** | 20KB | Developers | Implementation Plan |
| **AUDIT_UPSTREAM_EXECUTION_FRAMEWORK.md** | 21KB | Architects | Deep Technical Analysis |

---

## Key Findings (TL;DR)

### What We Discovered
- ⚠️ We re-implemented ~40% of upstream framework (order fills, TTL, position tracking, PnL)
- ✅ Our unique strategy logic (~60%) is valuable (zone detection, MTF gating, scoring)
- 🔴 High maintenance burden maintaining custom execution layer
- 🟡 Binance futures NOT supported in upstream examples

### What We Recommend
**Compatibility Layer Approach**:
1. Extract strategy core (framework-agnostic)
2. Create upstream adapter (`decide_trades_sd_v1`)
3. Keep CSV adapter (experiments, artifacts)
4. Reduce maintenance (delegate execution to framework)

### Next Steps
**Phase 1 PR** (detailed in all documents):
- Create `strategy_core.py` (~1000 lines)
- Create `decide_trades_adapter.py` (~200 lines)
- Rename `runner.py` → `csv_backtest_adapter.py`
- Add example notebook using `run_backtest_inline()`
- Document dual approach

---

## Upstream Framework Pattern (Quick Reference)

### Strategy Functions (User-Defined)
```python
def decide_trades(input: StrategyInput) -> list[TradeExecution]:
    position_manager = input.get_position_manager()
    # ... strategy logic ...
    if entry_signal:
        trades += position_manager.open_spot(pair, value, stop_loss, take_profit)
    if exit_signal:
        trades += position_manager.close_all()
    return trades
```

### Backtest Execution
```python
from tradeexecutor.backtest.backtest_runner import run_backtest_inline

result = run_backtest_inline(
    decide_trades=decide_trades,
    universe=strategy_universe,
    parameters=parameters,
)

state = result.state
trades = list(state.portfolio.get_all_trades())
```

**Found in**:
- `notebooks/single-backtest/bitcoin-ma.ipynb`
- `notebooks/single-backtest/matic-breakout.ipynb`
- 5+ other example notebooks

---

## Our Custom Implementation (Quick Reference)

### Current Structure
```
strategies/supply_demand_v1/
├── strategy.py (1,800 lines) - Strategy logic + order handling
├── runner.py (2,200 lines) - Backtest loop + artifacts
├── data_loader.py - Historical data
├── integrity.py - Validation
└── zone_tracker.py - State management
```

### Framework Overlap (Should Delegate to Upstream)
- ⚠️ Order lifecycle management (OrderState, pending/filled/cancelled)
- ⚠️ Fill simulation (`check_limit_order_fill()`)
- ⚠️ TTL tracking (cancel orders after N bars)
- ⚠️ Position state (pending_plans, open_positions)
- ⚠️ Breakeven management (`manage_trade_plan()`)
- ⚠️ PnL calculation (`calculate_pnl_with_costs()`)

### Unique Strategy Logic (Should Keep)
- ✅ Zone detection (DBR/RBD patterns)
- ✅ Multi-timeframe gating (HTF curve + ITF trend)
- ✅ Odds enhancer scoring
- ✅ Parallel execution
- ✅ CSV artifact generation

---

## Recommended Next PR Structure

### Phase 1: Extract Strategy Core

**Create**:
1. `strategies/supply_demand_v1/strategy_core.py`
   - Zone detection, scoring, gating (framework-agnostic)
   
2. `strategies/supply_demand_v1/decide_trades_adapter.py`
   - Upstream-compatible `decide_trades_sd_v1()` function
   
3. `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md`
   - Documentation of dual adapter approach
   
4. `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`
   - Example using `run_backtest_inline()`

**Rename**:
- `runner.py` → `csv_backtest_adapter.py`

**Modify**:
- `strategy.py` - Remove moved functions, import from strategy_core
- `README.md` - Document dual approach
- Tests - Update imports

**Validate**:
- Both adapters produce identical results
- No behavior changes
- All tests pass

---

## Questions & Answers

### Q: Why not just rewrite everything to use upstream?
**A**: CSV backtester is proven and generates artifacts we need for PR comparisons. Compatibility layer lets us keep it while enabling upstream integration.

### Q: Does upstream support Binance futures?
**A**: Not explicitly in examples. Our CSV adapter can handle futures semantics (shorts, leverage). Upstream adapter would be for spot initially.

### Q: How much work is Phase 1?
**A**: ~1 week (estimated):
- 2 days: Extract strategy_core.py
- 1 day: Create decide_trades_adapter.py
- 1 day: Refactor CSV adapter
- 1 day: Example notebook + docs
- 1 day: Testing and validation

### Q: Will this break existing workflows?
**A**: No. CSV adapter (`runner.py` renamed) keeps working as-is. Upstream adapter is additive.

### Q: What if upstream doesn't meet our needs?
**A**: We keep CSV adapter. Strategy core is portable - can be used with any execution framework.

---

## Related Documentation

- [Supply & Demand V1 Strategy README](strategies/supply_demand_v1/README.md)
- [Project Context](docs/PROJECT_CONTEXT.md)
- [Repository Map](docs/REPO_MAP.md)
- [Copilot Workflow Guidelines](docs/COPILOT_WORKFLOW.md)

---

## Status

✅ **Audit Complete**  
⏳ **Awaiting Review** - Review findings and approve Phase 1 plan  
⏳ **Next Action** - Implement Phase 1 (create strategy_core + adapters)

---

**Questions or feedback?** Open an issue or reach out to the team.
