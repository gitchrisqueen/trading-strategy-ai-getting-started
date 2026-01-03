# Upstream Trading Strategy Framework Audit - Executive Summary

**Format**: As requested in problem statement  
**Date**: 2026-01-03

---

## 1. Findings (Bullet List)

### Upstream Framework Architecture
- Upstream uses **clean separation**: strategy functions (`decide_trades`, `create_indicators`) + execution framework (`tradeexecutor`)
- Strategy functions are **pure logic**: receive `StrategyInput`, return `list[TradeExecution]`
- Framework handles **all execution concerns**: order placement, fills, position tracking, PnL, state management
- Framework provides **PositionManager** API: `open_spot()`, `close_all()`, `is_any_open()`, `get_current_cash()`
- Backtest orchestration via **`run_backtest_inline()`**: runs strategy in event loop, manages state
- **Binance futures NOT explicitly supported** in examples (only spot CEX and DEX)

### Our Custom Implementation Analysis
- **Re-implemented significant framework portions** (~40% of code):
  - Order lifecycle (OrderState enum, pending/filled/cancelled tracking)
  - TTL expiration logic (cancel orders after N bars)
  - Fill simulation (`check_limit_order_fill()` - checks if price touches limit)
  - Position state tracking (pending_plans, open_positions arrays)
  - Breakeven management (`manage_trade_plan()` - moves stop to breakeven)
  - Exit detection (`check_intrabar_exit()` - stop/target checks)
  - PnL calculation (`calculate_pnl_with_costs()` - applies fees/slippage)
  - Trade metrics (R-multiple, win rate, drawdown calculations)

- **Unique, valuable strategy logic** (~60% of code):
  - Supply & Demand zone detection (DBR/RBD pattern recognition)
  - Multi-timeframe gating (HTF curve + ITF trend classification)
  - Odds enhancer scoring (freshness + leg-out strength + base time + profit zone)
  - Zone freshness tracking (touch counting, invalidation)
  - Parallel execution infrastructure (ProcessPoolExecutor for multi-symbol)
  - CSV artifact generation (summary.json, trades.csv, zones.csv, manifest, violations)

### Architecture Issues Identified
- **High maintenance burden**: Must maintain order/position logic that upstream provides
- **Isolated from ecosystem**: Cannot use upstream analytics, visualizations, community tools
- **Tight coupling**: Strategy logic mixed with execution concerns in same files
- **Duplication risk**: Bug fixes must be done ourselves (e.g., look-ahead bias enforcement)

### Positive Observations
- **Working system**: CSV backtester is proven, generates reproducible artifacts
- **Futures semantics**: Our implementation supports shorts, leverage (even if upstream doesn't)
- **Custom experiments**: Parallel execution and artifact generation enable PR comparisons
- **Comprehensive testing**: Integrity checks, violation tracking, deterministic tests

---

## 2. Upstream Locations (Paths)

### Examples Showing decide_trades()

**File**: `notebooks/single-backtest/bitcoin-ma.ipynb`  
**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/notebooks/single-backtest/bitcoin-ma.ipynb`

**Function signature**:
```python
def decide_trades(input: StrategyInput) -> list[TradeExecution]:
    position_manager = input.get_position_manager()
    # ... strategy logic ...
    return trades
```

**Notes**:
- Receives `StrategyInput` with timestamp, indicators, state, universe
- Uses `position_manager.open_spot(pair, value, stop_loss, take_profit)` to open positions
- Uses `position_manager.close_all()` to close positions
- Returns list of `TradeExecution` objects (not custom TradePlan)

**Other examples**:
- `notebooks/single-backtest/matic-breakout.ipynb` (RSI + Bollinger Bands)
- `notebooks/single-backtest/multipair-atr-breakout.ipynb` (ATR breakout)
- `notebooks/single-backtest/eth-mfi.ipynb` (Money Flow Index)
- `notebooks/grid-search/bollinger-bands-matic-breakout.ipynb` (grid search)

### PositionManager.open_position / close_position

**Usage in notebooks**:
```python
# Open position
trades += position_manager.open_spot(
    pair=pair,
    value=cash * parameters.allocation,
    stop_loss=...,  # optional
    take_profit=...,  # optional
)

# Close all positions
trades += position_manager.close_all()

# Query state
is_open = position_manager.is_any_open()
cash = position_manager.get_current_cash()
```

**Expected location**: `PositionManager` is obtained from `StrategyInput.get_position_manager()`

**Notes**:
- Framework handles actual order execution, fills, state updates
- Strategy just expresses intent ("open this", "close that")
- No manual state tracking needed in strategy code

### run_backtest_inline()

**File**: All example notebooks use this  
**Example**: `notebooks/single-backtest/bitcoin-ma.ipynb`

**Usage**:
```python
from tradeexecutor.backtest.backtest_runner import run_backtest_inline

result = run_backtest_inline(
    name=parameters.id,
    engine_version="0.5",
    decide_trades=decide_trades,
    create_indicators=create_indicators,
    client=client,
    universe=strategy_universe,
    parameters=parameters,
    strategy_logging=False,
)

state = result.state
trades = list(state.portfolio.get_all_trades())
```

**Notes**:
- Entry point for backtest execution
- Calls `decide_trades()` in event loop for each timestamp
- Manages state object with portfolio, positions, trades
- Returns result with state, metrics, performance data

### Expected Dependency Locations (Not Accessible in CI)

**Package**: `trade-executor` expected at `../trade-executor` (editable install)

**Key modules** (inferred from imports):

#### Order/Trade Representation
- `tradeexecutor.state.trade.TradeExecution` - Trade object returned by decide_trades
- `tradeexecutor.state.position.Position` - Open position representation
- `tradeexecutor.state.portfolio.Portfolio` - Portfolio state with all positions/trades

#### Order Placement & Fill Simulation
- `tradeexecutor.backtest.backtest_runner.run_backtest_inline` - Main backtest orchestrator
- `PositionManager` (from StrategyInput) - API for opening/closing positions
  - `.open_spot(pair, value, stop_loss, take_profit)`
  - `.open_short(pair, value, stop_loss, take_profit)` (likely)
  - `.close_all()`
  - `.close_position(position)`

#### Fill Logic / Slippage / Fees / Position Accounting
**Location**: Likely `tradeexecutor.backtest.backtest_runner` module

**How it works** (inferred):
1. `run_backtest_inline()` orchestrates the event loop
2. For each decision cycle:
   - Calls `decide_trades()` with current state
   - Gets back list of `TradeExecution` objects
   - Simulates fills based on order type (market/limit)
   - Applies slippage and fees
   - Updates portfolio state
   - Tracks PnL and equity curve

**Position accounting**:
- `state.portfolio.get_all_trades()` - All executed trades
- `state.portfolio.get_open_positions()` - Current positions
- Performance metrics calculated automatically (Sharpe, max DD, etc.)

---

## 3. Our Code Overlap (Paths)

### strategies/supply_demand_v1/strategy.py

**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/strategy.py`

**Size**: 1,800+ lines, 40+ functions

#### Framework Overlap (Should be delegated to upstream):

| Function/Class | Lines | Purpose | Upstream Equivalent |
|----------------|-------|---------|---------------------|
| `OrderState` enum | 41-46 | Order states (PENDING/FILLED/CANCELLED) | Framework state |
| `TradePlan` dataclass | 141-196 | Order/position state (17 fields) | `TradeExecution` |
| `check_limit_order_fill()` | 1687-1767 | **Fill simulation** | Backtest runner |
| `manage_trade_plan()` | 1434-1486 | **Breakeven, exit management** | Framework |
| `check_intrabar_exit()` | 1374-1432 | **Stop/target detection** | Backtest runner |
| `calculate_pnl_with_costs()` | 1769-1825 | **PnL calculation** | Portfolio state |
| `calculate_r_multiple()` | 1488-1525 | **Trade metrics** | Performance analytics |

#### Unique Strategy Logic (Should stay):

| Function | Lines | Purpose |
|----------|-------|---------|
| `detect_zones_dbr_rbd()` | 354-510 | DBR/RBD pattern detection |
| `is_zone_fresh()` | 578-645 | Freshness tracking |
| `curve_location()` | 704-759 | HTF curve analysis |
| `trend_direction_itf()` | 761-860 | ITF trend detection |
| `should_allow_trade()` | 1058-1127 | Multi-timeframe gating |
| `odds_enhancer_score()` | 1129-1222 | Setup quality scoring |
| `build_trade_plan()` | 1224-1332 | Entry/stop/target calculation |

### strategies/supply_demand_v1/runner.py

**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/runner.py`

**Size**: 2,200+ lines, 20+ functions

#### Framework Overlap (Should be delegated to upstream):

| Code Section | Lines | Purpose | Upstream Equivalent |
|--------------|-------|---------|---------------------|
| `OrderRecord` dataclass | 333-356 | Order lifecycle tracking | Framework state |
| Order state arrays | 1021-1023 | `pending_plans`, `open_positions` | Portfolio state |
| TTL expiration loop | 1095-1110 | Cancel orders after N bars | Framework |
| Fill checking loop | 1110-1150 | Check if orders filled | Backtest runner |
| Position exit loop | 1150-1200 | Check stops/targets | Backtest runner |
| Backtest event loop | 907-1454 | Iterate candles, manage state | `run_backtest_inline()` |
| Metrics validation | 275-415 | Check for impossible metrics | Framework |

#### Unique Infrastructure (Should stay):

| Function | Lines | Purpose |
|----------|-------|---------|
| `run_backtests_parallel()` | 1597-1689 | Multi-process execution |
| `generate_synthetic_candles_mtf()` | 485-601 | Multi-timeframe test data |
| `load_candles_mtf_from_config()` | 752-905 | Historical data loading |
| `write_artifacts()` | 2081-2273 | CSV/JSON output |
| `run_backtest_experiment()` | 1732-2079 | Main entry point |

---

## 4. Recommendation (Next PR Outline)

### Problem Statement
- **Binance futures NOT supported** in upstream examples (only spot CEX/DEX)
- We **re-implemented 40%** of framework (order fills, TTL, position tracking, PnL)
- Our strategy logic is **tightly coupled** to custom CSV backtester
- **High maintenance burden**: must fix bugs ourselves (fills, TTL, look-ahead bias)

### Proposed Solution: Compatibility Layer

**Approach**: Create **dual adapter pattern** to preserve CSV backtester while enabling upstream integration.

```
Strategy Core (zone detection, scoring, gating)
       ├── Upstream Adapter (decide_trades_sd_v1)
       │      └── run_backtest_inline()
       └── CSV Adapter (csv_backtest_adapter.py)
              └── Custom backtest loop + artifacts
```

### Phase 1: Extract Strategy Core (Next PR)

#### Step 1.1: Create `strategy_core.py`

**New file**: `strategies/supply_demand_v1/strategy_core.py`

**Move these functions** (framework-agnostic):
```python
# Zone detection
detect_zones_dbr_rbd()
identify_boring_candles()
identify_exciting_candles()
compute_zone_lines_proximal_distal()

# Freshness
is_zone_fresh()

# Multi-timeframe
find_nearest_fresh_zones_htf()
curve_location()
trend_direction_itf()
detect_pivot_highs_lows()

# Scoring & gating
odds_enhancer_score()
should_allow_trade()

# Trade planning
build_trade_plan()  # Returns entry/stop/target prices
position_size()
```

**Estimated size**: ~1,000 lines (pure strategy logic)

#### Step 1.2: Create Upstream Adapter

**New file**: `strategies/supply_demand_v1/decide_trades_adapter.py`

```python
from tradeexecutor.strategy.pandas_trader.strategy_input import StrategyInput
from tradeexecutor.state.trade import TradeExecution
from .strategy_core import *

def decide_trades_sd_v1(input: StrategyInput) -> list[TradeExecution]:
    """Supply & Demand V1 strategy - upstream-compatible
    
    Wraps zone detection, scoring, gating logic to work with
    upstream TradingStrategy.ai execution framework.
    """
    # 1. Get inputs
    position_manager = input.get_position_manager()
    candles = input.strategy_universe.data_universe.candles
    params = input.parameters
    
    # 2. Detect zones (LTF)
    zones = detect_zones_dbr_rbd(candles['15m'], ...)
    
    # 3. Analyze HTF/ITF
    curve = curve_location(candles['4h'], zones)
    trend = trend_direction_itf(candles['1h'], ...)
    
    # 4. Score & filter
    scored = [odds_enhancer_score(z, ...) for z in zones]
    allowed = [z for z in scored if should_allow_trade(z, curve, trend, params)]
    
    # 5. Generate trades via PositionManager
    trades = []
    for zone in allowed:
        plan = build_trade_plan(zone, ...)
        if plan.planned_r >= params.min_reward_risk:
            if zone.zone_type == ZoneType.DEMAND:
                trades += position_manager.open_spot(
                    pair=..., value=plan.position_size,
                    stop_loss=plan.stop_loss, take_profit=plan.take_profit
                )
            else:
                trades += position_manager.open_short(...)
    
    return trades
```

**Benefits**:
- ✅ Strategy logic becomes **portable**
- ✅ Framework handles fills, TTL, position tracking, PnL
- ✅ Can use upstream analytics and visualizations
- ✅ Reduces maintenance (delegate execution to framework)

#### Step 1.3: Refactor CSV Runner

**Rename**: `runner.py` → `csv_backtest_adapter.py`

**Changes**:
- Import from `strategy_core.py` instead of `strategy.py`
- Keep order/position management (for now, to preserve working system)
- Keep parallel execution
- Keep artifact generation (summary.json, trades.csv, zones.csv, manifest, violations)
- Update docstring: "CSV-based backtest adapter for custom experiments"

**Rationale**: CSV runner is **proven**. Keep it as-is but clarify it's an **adapter**, not the only way to use the strategy.

#### Step 1.4: Create Example Notebook

**New file**: `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`

**Structure**:
```python
# Cell 1: Setup
from tradingstrategy.client import Client
from tradeexecutor.utils.binance import create_binance_universe
# ... other imports

# Cell 2: Parameters
class Parameters(StrategyParameters):
    symbols = ['BTC/USDT', 'ETH/USDT']
    min_setup_score = 6.0
    min_reward_risk = 3.0
    # ... other params

# Cell 3: Import strategy
from strategies.supply_demand_v1.decide_trades_adapter import decide_trades_sd_v1

# Cell 4: Run backtest
from tradeexecutor.backtest.backtest_runner import run_backtest_inline

result = run_backtest_inline(
    name="Supply & Demand V1",
    engine_version="0.5",
    decide_trades=decide_trades_sd_v1,
    client=client,
    universe=strategy_universe,
    parameters=parameters,
)

# Cell 5: Display results
state = result.state
trades = list(state.portfolio.get_all_trades())
print(f"Total trades: {len(trades)}")
# ... upstream analytics and charts
```

#### Step 1.5: Documentation

**New file**: `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md`

**Sections**:
1. **Two Ways to Use S&D Strategy**
   - Upstream adapter (for production, real data, upstream tools)
   - CSV adapter (for experiments, parallel execution, artifacts)

2. **Feature Comparison**
   
   | Feature | Upstream | CSV Adapter |
   |---------|----------|-------------|
   | Real market data | ✅ | ⚠️ Synthetic |
   | Upstream analytics | ✅ | ❌ |
   | Parallel execution | ❌ | ✅ |
   | Artifact generation | ❌ | ✅ |
   | Integrity checks | ❌ | ✅ |
   | Order dedupe | ✅ | Manual |
   | TTL expiration | ✅ | Manual |

3. **When to Use Each**
   - Upstream: Production trading, real data, community tools
   - CSV: Custom experiments, PR comparisons, parallel backtests

4. **Migration Path**
   - If upstream adds needed features (futures, artifacts), deprecate CSV adapter
   - Strategy core remains portable regardless

### Phase 2: Validate (Same PR or Follow-up)

**Testing**:
- [ ] Run upstream adapter on synthetic data
- [ ] Run CSV adapter on same data
- [ ] Compare results (should be identical initially)
- [ ] Document any differences

**Unit tests**:
- [ ] Test `strategy_core.py` functions in isolation
- [ ] Test `decide_trades_adapter.py` with mock StrategyInput
- [ ] Validate both adapters produce consistent zone detection

### Phase 3: Deprecate Redundant Code (Future PR)

**When**: After upstream adapter is validated and stable

**Remove** (delegate to framework):
- `check_limit_order_fill()` from strategy.py
- `manage_trade_plan()` from strategy.py
- Order lifecycle management from csv_backtest_adapter.py
- TTL tracking from csv_backtest_adapter.py
- PnL calculation from csv_backtest_adapter.py

**Keep**:
- Strategy core (zone detection, scoring, gating)
- CSV adapter (as legacy tool for experiments)
- Artifact generation (unique to CSV adapter)

### Benefits of This Approach

✅ **Preserves working system**: CSV backtester keeps working, artifacts unchanged  
✅ **Enables upstream integration**: Can use `run_backtest_inline()` and upstream tools  
✅ **Reduces maintenance**: Framework handles fills, TTL, PnL, bug fixes  
✅ **Future-proof**: Strategy logic is portable, not tied to one executor  
✅ **Best of both worlds**: CSV adapter for experiments, upstream for production  

### Risks & Mitigations

🟡 **Risk**: Refactoring introduces bugs  
✅ **Mitigation**: Keep CSV adapter as gold standard, compare results

🟡 **Risk**: Upstream may not support futures  
✅ **Mitigation**: CSV adapter handles futures, upstream handles spot (for now)

🟡 **Risk**: Dual systems to maintain  
✅ **Mitigation**: Deprecate CSV adapter once upstream has needed features

---

## Summary

### What We Found
- Upstream provides complete execution framework (fills, positions, PnL)
- We re-implemented 40% of it (order lifecycle, TTL, state tracking)
- Our unique strategy logic (60%) is valuable and should be preserved
- Binance futures NOT supported in upstream examples

### What We Recommend
- **Extract strategy core** to framework-agnostic module
- **Create upstream adapter** using `decide_trades()` pattern
- **Keep CSV adapter** for experiments and artifacts
- **Reduce maintenance** by delegating execution to framework

### Next PR Outline
1. Create `strategy_core.py` (~1000 lines, framework-agnostic)
2. Create `decide_trades_adapter.py` (~200 lines, upstream-compatible)
3. Rename `runner.py` → `csv_backtest_adapter.py` (clarify purpose)
4. Add example notebook using `run_backtest_inline()`
5. Document dual approach in `UPSTREAM_COMPATIBILITY.md`
6. Validate both adapters produce consistent results

### Files to Create/Modify
**Create**:
- `strategies/supply_demand_v1/strategy_core.py`
- `strategies/supply_demand_v1/decide_trades_adapter.py`
- `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md`
- `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`

**Rename**:
- `strategies/supply_demand_v1/runner.py` → `csv_backtest_adapter.py`

**Modify**:
- `strategies/supply_demand_v1/strategy.py` (remove moved functions)
- `strategies/supply_demand_v1/README.md` (document dual approach)
- Test files (update imports)

---

**Audit Complete**: 2026-01-03  
**Status**: Ready for team review and approval
