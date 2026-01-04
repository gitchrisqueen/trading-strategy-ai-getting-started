# Audit: Upstream TradingStrategy.ai Execution Framework

**Date**: 2026-01-03  
**Purpose**: Compare upstream Trading Strategy framework with custom Supply & Demand V1 implementation  
**Goal**: Identify opportunities to align with upstream patterns and reduce maintenance burden

---

## Executive Summary

This audit compares the **upstream TradingStrategy.ai execution framework** (as used in `notebooks/single-backtest/*.ipynb`) with our **custom Supply & Demand V1 runner and strategy** (`strategies/supply_demand_v1/`).

**Key Findings**:
1. ✅ Upstream framework provides complete order execution, position management, and backtest infrastructure
2. ⚠️ We have re-implemented significant portions of the framework (order fill logic, TTL tracking, position state, trade management)
3. ⚠️ Our custom implementation is tightly coupled to CSV-based backtesting rather than the upstream execution model
4. 🔄 Binance futures support is **not explicitly shown** in upstream examples (focused on DEX and spot CEX)

**Recommendation**: Create a **compatibility layer** that:
- Keeps our CSV-based backtester for now (proven, working)
- Refactors strategy to expose a `decide_trades`-like interface
- Makes runner a thin adapter that bridges our logic to standard patterns

---

## 1. Upstream Framework Structure

### 1.1 Key Components

The upstream framework follows a **strategy → executor → backtest** pattern:

```
Strategy Functions (user-defined)
    ├── create_indicators()
    ├── decide_trades()
    └── (optional) create_trading_universe()
            ↓
Execution Framework (tradeexecutor)
    ├── PositionManager
    ├── StrategyInput
    ├── TradeExecution
    └── BacktestRunner
            ↓
Results & Analysis
    ├── State (portfolio, positions, trades)
    ├── Performance Metrics
    └── Visualizations
```

### 1.2 File Locations: Upstream Examples

#### Example Notebook: `notebooks/single-backtest/bitcoin-ma.ipynb`

**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/notebooks/single-backtest/bitcoin-ma.ipynb`

**Key Sections**:

1. **create_indicators() function**:
```python
def create_indicators(
    timestamp: datetime.datetime | None,
    parameters: StrategyParameters,
    strategy_universe: TradingStrategyUniverse,
    execution_context: ExecutionContext
):
    indicators = IndicatorSet()
    indicators.add(
        "ma",
        pandas_ta.sma,
        {"length": parameters.ma_length},
        IndicatorSource.close_price,
    )
    return indicators
```

2. **decide_trades() function**:
```python
def decide_trades(
    input: StrategyInput,
) -> list[TradeExecution]:
    parameters = input.parameters
    position_manager = input.get_position_manager()
    state = input.state
    timestamp = input.timestamp
    indicators = input.indicators
    strategy_universe = input.strategy_universe

    pair = strategy_universe.get_single_pair()
    cash = position_manager.get_current_cash()

    # Get indicators
    close_price = indicators.get_price()
    moving_average = indicators.get_indicator_value("ma")

    # Trading logic
    trades = []
    if not position_manager.is_any_open():
        if close_price > moving_average:
            trades += position_manager.open_spot(
                pair,
                value=cash * parameters.allocation,
            )
    else:
        if close_price < moving_average:
            trades += position_manager.close_all()

    return trades
```

3. **run_backtest_inline() call**:
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
trade_count = len(list(state.portfolio.get_all_trades()))
```

**Similar patterns in**:
- `notebooks/single-backtest/matic-breakout.ipynb`
- `notebooks/single-backtest/multipair-atr-breakout.ipynb`
- `notebooks/single-backtest/eth-mfi.ipynb`

### 1.3 Upstream Components (Expected in trade-executor)

**Note**: The `trade-executor` package is expected at `../trade-executor` but is not present in this CI environment. Based on imports in notebooks:

#### Key Imports from `tradeexecutor`:
```python
from tradeexecutor.backtest.backtest_runner import run_backtest_inline
from tradeexecutor.state.trade import TradeExecution
from tradeexecutor.strategy.pandas_trader.strategy_input import StrategyInput
from tradeexecutor.strategy.pandas_trader.indicator import IndicatorSet, IndicatorSource
from tradeexecutor.strategy.parameters import StrategyParameters
from tradeexecutor.strategy.trading_strategy_universe import TradingStrategyUniverse
```

#### Expected Modules (Not Available to Inspect):

**Order/Trade Representation**:
- `tradeexecutor.state.trade.TradeExecution` - Represents a trade
- `tradeexecutor.state.position.Position` - Represents an open position
- `tradeexecutor.state.portfolio.Portfolio` - Manages portfolio state

**Order Placement**:
- `PositionManager.open_spot()` - Open spot position
- `PositionManager.open_short()` - Open short position (likely)
- `PositionManager.close_all()` - Close all positions
- `PositionManager.close_position()` - Close specific position

**Fill Simulation**:
- Likely handled in `tradeexecutor.backtest.backtest_runner`
- Slippage/fees applied during backtest execution
- Position accounting automatic

**Trade State Tracking**:
- `state.portfolio` - Portfolio state
- `state.portfolio.get_all_trades()` - All executed trades
- `state.portfolio.get_open_positions()` - Current positions

---

## 2. Our Custom Implementation

### 2.1 File Structure

```
strategies/supply_demand_v1/
├── strategy.py          # Core strategy logic + order handling
├── runner.py            # Backtest execution + order fills
├── data_loader.py       # Historical data loading
├── integrity.py         # Validation checks
└── zone_tracker.py      # Zone state management
```

### 2.2 Responsibilities: strategy.py

**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/strategy.py`

**Functions** (40+ functions, 1800+ lines):

#### Core Strategy Logic (Should Stay):
- `detect_zones_dbr_rbd()` - Zone detection (DBR/RBD patterns)
- `is_zone_fresh()` - Freshness tracking
- `curve_location()` - HTF curve analysis
- `trend_direction_itf()` - ITF trend detection
- `odds_enhancer_score()` - Setup scoring
- `should_allow_trade()` - Multi-timeframe gating

#### Trade Planning (Similar to decide_trades):
- `build_trade_plan()` - Generate entry/stop/target
- `position_size()` - Calculate position size

#### Order/Execution Logic (Framework Overlap):
- ⚠️ `check_limit_order_fill()` - **Fill simulation logic**
- ⚠️ `manage_trade_plan()` - **Position management (breakeven, exits)**
- ⚠️ `check_intrabar_exit()` - **Stop/target checks**
- ⚠️ `calculate_pnl_with_costs()` - **PnL calculation with fees**
- ⚠️ `calculate_r_multiple()` - **Trade metrics**

**Key Data Structures**:

```python
class OrderState(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

@dataclass
class TradePlan:
    zone: Zone
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    planned_r: float
    score: float
    placed_at_idx: int
    order_state: OrderState = OrderState.PENDING
    filled_at_idx: Optional[int] = None
    # ... (17 fields total)
```

### 2.3 Responsibilities: runner.py

**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/runner.py`

**Functions** (20+ functions, 2200+ lines):

#### Backtest Orchestration:
- `run_backtest_experiment()` - Main entry point
- `execute_backtest_for_symbol()` - Per-symbol backtest
- `run_backtests_parallel()` - Parallel execution

#### Order Lifecycle Management (Framework Overlap):
- ⚠️ **Order placement tracking** (lines 1021-1023):
  ```python
  orders = []  # Track all order lifecycle events
  pending_plans = []  # Plans with pending orders
  open_positions = []  # Plans with filled orders (active positions)
  ```

- ⚠️ **Fill checking** (lines 1095-1110):
  ```python
  # Check for fills on pending orders (LTF fills only)
  for plan in pending_plans[:]:
      if plan.order_state == OrderState.PENDING:
          # Check TTL expiration first
          if (current_ltf_idx - plan.placed_at_idx) >= params.ttl_bars:
              plan.order_state = OrderState.CANCELLED
              pending_plans.remove(plan)
              funnel.orders_expired_ttl += 1
  ```

- ⚠️ **Position state management** (lines 1023, 1110-1150):
  - Tracking open positions
  - Managing breakeven moves
  - Exit detection

- ⚠️ **Trade lifecycle** (OrderRecord dataclass, lines 333-356):
  ```python
  @dataclass
  class OrderRecord:
      """Record of an order's complete lifecycle"""
      symbol: str
      side: str  # "LONG" or "SHORT"
      entry_price: float
      stop_loss: float
      take_profit: float
      # ... 17 fields tracking full lifecycle
  ```

#### Artifact Generation:
- `write_artifacts()` - CSV/JSON output
- `create_artifacts_folder()` - Directory management
- Summary metrics, integrity reports

---

## 3. Overlap Analysis: What We Re-Implemented

### 3.1 Order Management

| Responsibility | Upstream | Our Implementation | Location |
|----------------|----------|-------------------|----------|
| **Order representation** | `TradeExecution` | `TradePlan` + `OrderState` | `strategy.py:141-196` |
| **Order placement** | `PositionManager.open_*()` | `build_trade_plan()` | `strategy.py:1224-1332` |
| **Fill simulation** | Backtest runner | `check_limit_order_fill()` | `strategy.py:1687-1767` |
| **TTL tracking** | Likely in executor | Custom loop in runner | `runner.py:1095-1110` |
| **Position tracking** | `state.portfolio` | `pending_plans` + `open_positions` | `runner.py:1021-1023` |

### 3.2 Trade Management

| Responsibility | Upstream | Our Implementation | Location |
|----------------|----------|-------------------|----------|
| **Breakeven moves** | Likely in executor | `manage_trade_plan()` | `strategy.py:1434-1486` |
| **Stop/target checks** | Backtest runner | `check_intrabar_exit()` | `strategy.py:1374-1432` |
| **PnL calculation** | `state.portfolio` | `calculate_pnl_with_costs()` | `strategy.py:1769-1825` |
| **Trade metrics** | Performance analytics | Custom in runner | `runner.py:275-415` |

### 3.3 Backtest Infrastructure

| Responsibility | Upstream | Our Implementation | Location |
|----------------|----------|-------------------|----------|
| **Backtest loop** | `run_backtest_inline()` | `execute_backtest_for_symbol()` | `runner.py:907-1454` |
| **State management** | `state` object | Custom equity/position tracking | `runner.py:1021-1150` |
| **Results output** | `state.portfolio` | CSV/JSON artifacts | `runner.py:2081-2273` |

### 3.4 Unique to Our Implementation

✅ **These are genuinely unique** (not framework overlap):

- **Supply & Demand zone detection**: `detect_zones_dbr_rbd()`
- **Multi-timeframe gating**: `curve_location()`, `trend_direction_itf()`, `should_allow_trade()`
- **Odds enhancer scoring**: `odds_enhancer_score()`
- **Freshness tracking**: `is_zone_fresh()`
- **Synthetic candle generation**: `generate_synthetic_candles_mtf()`
- **Parallel execution**: `run_backtests_parallel()`
- **CSV-based artifacts**: Complete experiment tracking

---

## 4. Binance Futures Support Analysis

### 4.1 Current State in Upstream Examples

**Upstream notebook examples use**:
- `from tradeexecutor.utils.binance import create_binance_universe`
- Focus on **spot markets** (BTC/USDT, ETH/USDT, MATIC/USDT)
- No explicit futures examples found

**Examples found**:
- `notebooks/single-backtest/matic-breakout.ipynb` - Binance spot
- `notebooks/single-backtest/multipair-atr-breakout.ipynb` - Binance spot
- DEX examples (Uniswap, etc.)

### 4.2 Our Custom Implementation

**Supports futures-specific features**:
- Short positions (`side = "SHORT"`)
- Funding rates (planned, not implemented)
- Position sizing for leverage (parameters support it)

**However**: Our backtester uses **synthetic candles** or **CSV data**, not live Binance futures data.

### 4.3 Futures Support Conclusion

🔴 **Binance futures execution is NOT explicitly supported in upstream examples**

✅ Our custom implementation **can handle futures semantics** (shorts, leverage) but doesn't integrate with upstream Binance API

---

## 5. Recommendations

### 5.1 Compatibility Layer Approach

**Goal**: Align with upstream patterns while preserving our working implementation.

#### Phase 1: Refactor Strategy Interface (Next PR)

**Create**: `strategies/supply_demand_v1/decide_trades.py`

```python
def decide_trades_sd_v1(
    input: StrategyInput,
) -> list[TradeExecution]:
    """
    Upstream-compatible decide_trades() function.
    
    Wraps our zone detection, scoring, and trade planning logic.
    Returns TradeExecution objects instead of TradePlan.
    """
    # 1. Get current state
    timestamp = input.timestamp
    candles = input.strategy_universe.data_universe.candles
    position_manager = input.get_position_manager()
    
    # 2. Detect zones (HTF, ITF, LTF)
    ltf_zones = detect_zones_dbr_rbd(candles['15m'], ...)
    
    # 3. Analyze HTF/ITF
    curve = curve_location(candles['4h'], ltf_zones)
    trend = trend_direction_itf(candles['1h'], ...)
    
    # 4. Score setups
    scored_zones = [odds_enhancer_score(z, ...) for z in ltf_zones]
    
    # 5. Filter by gating rules
    allowed_zones = [z for z in scored_zones if should_allow_trade(z, curve, trend)]
    
    # 6. Build trade plans
    trades = []
    for zone in allowed_zones:
        if zone.score >= params.min_setup_score:
            # Use position_manager to open position
            trades += position_manager.open_spot(
                pair=...,
                value=...,
                stop_loss=zone.stop_loss,
                take_profit=zone.take_profit,
            )
    
    return trades
```

**Benefits**:
- Strategy logic becomes **framework-agnostic**
- Can use upstream `run_backtest_inline()` in future
- Preserves our zone detection, scoring, gating

#### Phase 2: Keep CSV Runner as Adapter

**Modify**: `strategies/supply_demand_v1/runner.py`

- Rename to `csv_backtest_adapter.py`
- Keep synthetic candle generation
- Keep parallel execution
- Keep artifact generation
- **But**: Call `decide_trades_sd_v1()` internally instead of duplicating logic

#### Phase 3: Documentation

**Create**: `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md`

- Explain how to use S&D strategy with upstream framework
- Document CSV runner as alternative for custom experiments
- Compare performance/features of both approaches

### 5.2 Specific Code Changes (Next PR Outline)

#### Step 1: Extract Strategy Core

**File**: `strategies/supply_demand_v1/strategy_core.py`

**Move these functions** (keep framework-agnostic):
- `detect_zones_dbr_rbd()`
- `is_zone_fresh()`
- `curve_location()`
- `trend_direction_itf()`
- `odds_enhancer_score()`
- `should_allow_trade()`

#### Step 2: Create Upstream Adapter

**File**: `strategies/supply_demand_v1/decide_trades.py`

**New function**:
- `decide_trades_sd_v1()` - Upstream-compatible interface

#### Step 3: Create Example Notebook

**File**: `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`

**Structure**:
1. Use `create_binance_universe()` for real data
2. Call `run_backtest_inline(decide_trades=decide_trades_sd_v1, ...)`
3. Show results with upstream analytics

#### Step 4: Keep CSV Runner

**Rename**: `runner.py` → `csv_backtest_adapter.py`

**Update**:
- Import from `strategy_core.py`
- Import from `decide_trades.py`
- Keep parallel execution, artifacts, integrity checks

### 5.3 Benefits of Compatibility Layer

✅ **Preserves current work**:
- CSV-based backtester keeps working
- Synthetic candles still available
- Parallel execution retained
- Integrity checks maintained

✅ **Enables upstream integration**:
- Can use `run_backtest_inline()` with real data
- Access upstream analytics/visualizations
- Leverage upstream position management

✅ **Reduces maintenance**:
- Don't re-implement order fills, TTL, PnL
- Framework handles edge cases
- Focus on strategy logic

✅ **Future-proof**:
- If upstream adds futures support, we can adopt it
- Strategy logic is portable
- CSV runner remains for custom experiments

---

## 6. Risk Analysis

### 6.1 Risks of Current Approach

🔴 **High maintenance burden**:
- Must maintain custom order fills, TTL, position tracking
- Bug fixes must be done ourselves (e.g., look-ahead bias, R-multiple enforcement)

🟡 **Limited ecosystem access**:
- Can't use upstream analytics, visualizations
- Can't leverage community strategies
- Miss framework improvements

🟡 **Futures support unclear**:
- Upstream may not support futures
- Our implementation is isolated

### 6.2 Risks of Compatibility Layer

🟡 **Refactoring effort**:
- Must extract strategy core carefully
- Need to test both runners
- Documentation overhead

🟡 **Dual maintenance** (temporary):
- CSV runner + upstream adapter
- May have behavior differences

🟢 **Mitigations**:
- Keep CSV runner as "gold standard"
- Validate upstream adapter against CSV results
- Comprehensive integrity tests

---

## 7. Decision Matrix

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **Keep current** | ✅ Working<br>✅ Custom experiments<br>✅ Proven | 🔴 High maintenance<br>🔴 Isolated<br>🔴 Re-implements framework | ❌ Not sustainable |
| **Rewrite from scratch** | ✅ Clean slate<br>✅ Upstream patterns | 🔴 Lose CSV runner<br>🔴 Lose experiments<br>🔴 High risk | ❌ Too risky |
| **Compatibility layer** | ✅ Preserves work<br>✅ Enables upstream<br>✅ Reduces maintenance | 🟡 Refactoring effort<br>🟡 Dual systems | ✅ **Recommended** |

---

## 8. Next Steps

### Immediate Actions

1. ✅ **Create this audit document** (Done)
2. ⏳ **Review with team** - Discuss approach
3. ⏳ **Plan refactoring PR** - Break into phases
4. ⏳ **Set up test harness** - Validate both runners produce same results

### Phase 1 PR: Extract Strategy Core

- [ ] Create `strategy_core.py` with framework-agnostic functions
- [ ] Add unit tests for strategy core
- [ ] Update runner to import from strategy_core
- [ ] Validate no behavior change (run experiments)

### Phase 2 PR: Create Upstream Adapter

- [ ] Create `decide_trades.py` with upstream interface
- [ ] Create example notebook using `run_backtest_inline()`
- [ ] Document differences between CSV runner and upstream
- [ ] Add tests comparing results

### Phase 3 PR: Deprecate Redundant Code

- [ ] Remove order fill logic from strategy.py (use upstream)
- [ ] Remove TTL tracking from runner.py (use upstream)
- [ ] Keep CSV runner as legacy/custom experiment tool
- [ ] Update documentation

---

## 9. Conclusion

Our custom Supply & Demand V1 implementation has **significant overlap** with the upstream TradingStrategy.ai execution framework. We've re-implemented:

- ⚠️ Order management (placement, fills, TTL)
- ⚠️ Position tracking (state, breakeven, exits)
- ⚠️ Trade lifecycle (PnL, metrics)

**The core strategy logic** (zone detection, scoring, gating) is **genuinely unique** and valuable.

**Recommendation**: Adopt a **compatibility layer** approach that:
1. Extracts strategy logic to framework-agnostic core
2. Creates upstream adapter (`decide_trades_sd_v1`)
3. Keeps CSV runner for custom experiments
4. Reduces maintenance by delegating order/position management to framework

This preserves our work while aligning with upstream patterns and reducing long-term maintenance burden.

---

## Appendix A: File Reference

### Upstream Examples

- `notebooks/single-backtest/bitcoin-ma.ipynb`
- `notebooks/single-backtest/matic-breakout.ipynb`
- `notebooks/single-backtest/multipair-atr-breakout.ipynb`
- `notebooks/single-backtest/eth-mfi.ipynb`

### Our Implementation

- `strategies/supply_demand_v1/strategy.py` (1800+ lines)
- `strategies/supply_demand_v1/runner.py` (2200+ lines)
- `strategies/supply_demand_v1/data_loader.py`
- `strategies/supply_demand_v1/integrity.py`
- `strategies/supply_demand_v1/zone_tracker.py`

### Expected Upstream Modules (Not Inspected)

- `tradeexecutor.backtest.backtest_runner`
- `tradeexecutor.state.trade`
- `tradeexecutor.state.position`
- `tradeexecutor.state.portfolio`
- `tradeexecutor.strategy.pandas_trader.strategy_input`

---

**Audit Completed**: 2026-01-03  
**Author**: GitHub Copilot  
**Status**: Ready for Review
