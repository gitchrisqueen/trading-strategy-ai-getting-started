# Upstream Trading Strategy Framework Audit - Summary Findings

**Date**: 2026-01-03  
**Repo**: trading-strategy-ai-getting-started (fork)

---

## 1. Findings (Bullet List)

### Upstream Framework Pattern
- ✅ Upstream uses **strategy function + executor framework** separation
- ✅ Strategy provides `decide_trades()` and `create_indicators()`
- ✅ Framework handles order placement, fills, position tracking, PnL
- ✅ Framework provides `PositionManager` for opening/closing positions
- ✅ Backtest orchestration via `run_backtest_inline()`
- ⚠️ No explicit Binance **futures** support found (only spot CEX examples)

### Our Custom Implementation
- ⚠️ We **re-implemented** significant portions of the framework:
  - Order lifecycle management (pending → filled → cancelled)
  - TTL tracking (time-to-live for limit orders)
  - Fill simulation logic (`check_limit_order_fill`)
  - Position state tracking (open positions, breakeven moves)
  - PnL calculation with fees/slippage
  - Trade metrics (R-multiples, win rate, drawdown)
- ✅ We have **unique, valuable** strategy logic:
  - Supply & Demand zone detection (DBR/RBD patterns)
  - Multi-timeframe gating (HTF curve + ITF trend)
  - Odds enhancer scoring (freshness, leg-out, base time)
  - Parallel execution infrastructure
  - CSV-based artifact generation for PR comparisons
- ⚠️ Our implementation is **tightly coupled** to custom CSV backtester
- ✅ Our implementation **does support futures semantics** (shorts, leverage)

### Architectural Observations
- 🔴 **High maintenance burden**: We maintain order/position logic that upstream already provides
- 🟡 **Isolated ecosystem**: Can't easily use upstream analytics, visualizations, community strategies
- ✅ **Working system**: Our CSV backtester is proven and produces machine-readable artifacts
- 🟡 **Futures gap**: Upstream may not support Binance futures; our needs may exceed their scope

---

## 2. Upstream Locations (Paths)

### Examples Showing Framework Pattern

#### `notebooks/single-backtest/bitcoin-ma.ipynb`
**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/notebooks/single-backtest/bitcoin-ma.ipynb`

**Key functions**:
- `create_indicators()` - Defines technical indicators
- `decide_trades(input: StrategyInput)` - Strategy logic, returns `list[TradeExecution]`
- Uses `position_manager.open_spot()` and `position_manager.close_all()`
- Calls `run_backtest_inline()` to execute

**Pattern**:
```python
def decide_trades(input: StrategyInput) -> list[TradeExecution]:
    position_manager = input.get_position_manager()
    # ... strategy logic ...
    if entry_signal:
        trades += position_manager.open_spot(pair, value=...)
    if exit_signal:
        trades += position_manager.close_all()
    return trades

result = run_backtest_inline(
    decide_trades=decide_trades,
    create_indicators=create_indicators,
    universe=strategy_universe,
    parameters=parameters,
)
```

#### Other Examples with Same Pattern
- `notebooks/single-backtest/matic-breakout.ipynb` - RSI + Bollinger Bands
- `notebooks/single-backtest/multipair-atr-breakout.ipynb` - ATR breakout, multiple pairs
- `notebooks/single-backtest/eth-mfi.ipynb` - Money Flow Index volume indicator
- `notebooks/grid-search/bollinger-bands-matic-breakout.ipynb` - Grid search example

### Expected Upstream Module Locations

**Note**: `trade-executor` package expected at `../trade-executor` (not present in CI environment)

Based on imports found in notebooks:

#### Order/Trade Representation
- `tradeexecutor.state.trade.TradeExecution` - Trade object
- `tradeexecutor.state.position.Position` - Position object
- `tradeexecutor.state.portfolio.Portfolio` - Portfolio state

#### Order Placement
- `PositionManager` (from `StrategyInput.get_position_manager()`)
  - `.open_spot(pair, value, stop_loss, take_profit)` - Open spot position
  - `.close_all()` - Close all positions
  - `.close_position(position)` - Close specific position
  - `.is_any_open()` - Check if any positions open
  - `.get_current_cash()` - Get available cash

#### Fill Simulation / Slippage / Fees / Position Accounting
**Location**: Likely in `tradeexecutor.backtest.backtest_runner`

**How it works** (inferred):
- `run_backtest_inline()` orchestrates the backtest loop
- For each decision cycle:
  1. Calls `decide_trades()`
  2. Executes returned `TradeExecution` objects
  3. Simulates fills (market/limit orders)
  4. Applies slippage and fees
  5. Updates portfolio state
  6. Tracks PnL and positions

**Position Accounting**:
- `state.portfolio` - Portfolio object with all trades and positions
- `state.portfolio.get_all_trades()` - All executed trades
- `state.portfolio.get_open_positions()` - Current open positions
- Performance metrics calculated automatically

### Imports Summary
```python
# Backtest runner
from tradeexecutor.backtest.backtest_runner import run_backtest_inline

# Strategy interface
from tradeexecutor.strategy.pandas_trader.strategy_input import StrategyInput
from tradeexecutor.state.trade import TradeExecution

# Indicators
from tradeexecutor.strategy.pandas_trader.indicator import IndicatorSet, IndicatorSource

# Universe and parameters
from tradeexecutor.strategy.trading_strategy_universe import TradingStrategyUniverse
from tradeexecutor.strategy.parameters import StrategyParameters

# Binance data
from tradeexecutor.utils.binance import create_binance_universe
```

---

## 3. Our Code Overlap (Paths)

### `strategies/supply_demand_v1/strategy.py`
**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/strategy.py`

**Size**: 1,800+ lines, 40+ functions

#### Framework Overlap (Should Be Delegated to Upstream):

**Order State Management**:
- Lines 41-46: `OrderState` enum (PENDING, FILLED, CANCELLED)
- Lines 141-196: `TradePlan` dataclass (17 fields tracking order/position state)
  - `order_state`, `placed_at_idx`, `filled_at_idx`
  - Entry/stop/target prices, position size, risk
  - Planned/realized R-multiples

**Fill Logic**:
- Lines 1687-1767: `check_limit_order_fill()` - **Simulates limit order fills**
  - Checks if candle low/high touches limit price
  - Applies slippage and fees
  - Updates order state to FILLED
  - Sets `filled_at_idx`

**Position Management**:
- Lines 1434-1486: `manage_trade_plan()` - **Manages open positions**
  - Moves stop to breakeven at configurable R-multiple
  - Signals exit at take-profit target
  - Returns "HOLD" or "EXIT"

**Stop/Target Checks**:
- Lines 1374-1432: `check_intrabar_exit()` - **Intrabar stop/target detection**
  - Uses intrabar lows/highs to detect exits
  - Returns exit type: "STOP_LOSS" or "TAKE_PROFIT"

**PnL Calculation**:
- Lines 1769-1825: `calculate_pnl_with_costs()` - **Calculates trade PnL**
  - Applies entry/exit fees
  - Calculates gross/net profit
  - Returns PnL amount

**Trade Metrics**:
- Lines 1488-1525: `calculate_r_multiple()` - **Calculates reward/risk ratio**

#### Unique Strategy Logic (Should Stay):

**Zone Detection**:
- Lines 354-510: `detect_zones_dbr_rbd()` - DBR/RBD pattern detection
- Lines 288-318: `identify_boring_candles()`
- Lines 320-352: `identify_exciting_candles()`
- Lines 512-576: `compute_zone_lines_proximal_distal()`

**Freshness Tracking**:
- Lines 578-645: `is_zone_fresh()` - Zone freshness logic

**Multi-Timeframe Analysis**:
- Lines 647-702: `find_nearest_fresh_zones_htf()` - HTF zone finding
- Lines 704-759: `curve_location()` - Price location in HTF range
- Lines 761-860: `trend_direction_itf()` - ITF trend detection
- Lines 1547-1598: `detect_pivot_highs_lows()` - Pivot detection

**Gating Logic**:
- Lines 1058-1127: `should_allow_trade()` - Multi-timeframe gating rules

**Scoring**:
- Lines 1129-1222: `odds_enhancer_score()` - Setup quality scoring

**Trade Planning**:
- Lines 1224-1332: `build_trade_plan()` - Entry/stop/target calculation
- Lines 1334-1372: `position_size()` - Position sizing

### `strategies/supply_demand_v1/runner.py`
**Path**: `/home/runner/work/trading-strategy-ai-getting-started/trading-strategy-ai-getting-started/strategies/supply_demand_v1/runner.py`

**Size**: 2,200+ lines, 20+ functions

#### Framework Overlap (Should Be Delegated to Upstream):

**Order Lifecycle Management**:
- Lines 333-356: `OrderRecord` dataclass - **Tracks complete order lifecycle**
  - Symbol, side, prices, state, timestamps
  - Fill events, cancellation events

- Lines 1021-1023: **Order state tracking**:
  ```python
  orders = []  # Track all order lifecycle events
  pending_plans = []  # Plans with pending orders
  open_positions = []  # Plans with filled orders (active positions)
  ```

**Fill Checking Loop**:
- Lines 1095-1110: **TTL expiration checking**:
  ```python
  for plan in pending_plans[:]:
      if plan.order_state == OrderState.PENDING:
          # Check TTL expiration first
          if (current_ltf_idx - plan.placed_at_idx) >= params.ttl_bars:
              plan.order_state = OrderState.CANCELLED
              pending_plans.remove(plan)
              funnel.orders_expired_ttl += 1
  ```

- Lines 1110-1150: **Fill simulation and position management**:
  - Check if limit orders filled
  - Move filled plans to `open_positions`
  - Track fills in `OrderRecord`

**Position State Management**:
- Lines 1150-1200: **Exit detection**:
  - Check stops/targets on open positions
  - Calculate PnL
  - Remove from `open_positions`

**Trade Metrics**:
- Lines 275-415: `check_metrics_consistency()` - **Validate metrics**
  - Checks for impossible metrics (max_drawdown = 0 with trades)
  - Validates R-multiples vs PnL

**Backtest Loop**:
- Lines 907-1454: `execute_backtest_for_symbol()` - **Main backtest loop**
  - Iterates through candles
  - Checks pending orders
  - Manages open positions
  - Calculates equity curve

#### Unique Infrastructure (Should Stay):

**Parallel Execution**:
- Lines 1597-1689: `run_backtests_parallel()` - Multi-process execution

**Synthetic Data Generation**:
- Lines 417-484: `generate_synthetic_candles()` - Single timeframe
- Lines 485-601: `generate_synthetic_candles_mtf()` - Multi-timeframe

**Data Loading**:
- Lines 603-750: `load_candles_from_config()` - Historical data loading
- Lines 752-905: `load_candles_mtf_from_config()` - Multi-timeframe loading

**Artifact Generation**:
- Lines 2081-2273: `write_artifacts()` - **CSV/JSON output**
  - summary.json (aggregate + per-symbol metrics)
  - trades.csv (all trades with full details)
  - zones.csv (all zones with scoring)
  - run_manifest.json (git commit, config, timestamp)
  - violations.json (integrity check results)

**Experiment Orchestration**:
- Lines 1732-2079: `run_backtest_experiment()` - Main entry point
- Lines 1691-1695: `load_config()` - YAML config loading
- Lines 1697-1713: `get_git_info()` - Git metadata
- Lines 1715-1730: `create_artifacts_folder()` - Directory management

---

## 4. Recommendation (Next PR Outline)

### Compatibility Layer Approach

**Goal**: Align with upstream patterns while preserving our proven CSV backtester.

### Phase 1: Extract Strategy Core (Next PR)

**Status**: ⚠️ Binance futures execution not explicitly supported upstream

**Recommendation**: Create compatibility layer to enable future upstream integration while keeping CSV runner.

#### Step 1.1: Create `strategy_core.py`

**New file**: `strategies/supply_demand_v1/strategy_core.py`

**Move these functions** (framework-agnostic strategy logic):
```python
# Zone detection
- detect_zones_dbr_rbd()
- identify_boring_candles()
- identify_exciting_candles()
- compute_zone_lines_proximal_distal()

# Freshness
- is_zone_fresh()

# Multi-timeframe analysis
- find_nearest_fresh_zones_htf()
- curve_location()
- trend_direction_itf()
- detect_pivot_highs_lows()

# Scoring and gating
- odds_enhancer_score()
- should_allow_trade()

# Trade planning (entry/stop/target calculation)
- build_trade_plan()
- position_size()
```

**Keep in `strategy.py`** (framework-specific, to be refactored later):
```python
# Order/position management (eventually delegate to upstream)
- check_limit_order_fill()
- manage_trade_plan()
- check_intrabar_exit()
- calculate_pnl_with_costs()
- calculate_r_multiple()
```

#### Step 1.2: Create Upstream Adapter

**New file**: `strategies/supply_demand_v1/decide_trades_adapter.py`

**Function**: `decide_trades_sd_v1(input: StrategyInput) -> list[TradeExecution]`

**Structure**:
```python
from tradeexecutor.strategy.pandas_trader.strategy_input import StrategyInput
from tradeexecutor.state.trade import TradeExecution
from .strategy_core import (
    detect_zones_dbr_rbd,
    curve_location,
    trend_direction_itf,
    odds_enhancer_score,
    should_allow_trade,
    build_trade_plan,
)

def decide_trades_sd_v1(input: StrategyInput) -> list[TradeExecution]:
    """Supply & Demand V1 strategy in upstream-compatible format
    
    This adapter wraps our zone detection, scoring, and gating logic
    to work with the upstream TradingStrategy.ai execution framework.
    """
    # 1. Extract input
    position_manager = input.get_position_manager()
    timestamp = input.timestamp
    candles = input.strategy_universe.data_universe.candles
    parameters = input.parameters
    
    # 2. Detect zones on LTF
    ltf_zones = detect_zones_dbr_rbd(
        candles_ltf=candles['15m'],
        min_base_candles=parameters.min_base_candles,
        max_base_candles=parameters.max_base_candles,
    )
    
    # 3. Analyze HTF curve and ITF trend
    curve = curve_location(candles['4h'], ltf_zones, timestamp)
    trend = trend_direction_itf(candles['1h'], parameters.pivot_len)
    
    # 4. Score setups
    scored_zones = []
    for zone in ltf_zones:
        score = odds_enhancer_score(zone, opposing_zone=None, params=parameters)
        zone.score = score
        scored_zones.append(zone)
    
    # 5. Filter by gating rules
    allowed_zones = [
        z for z in scored_zones 
        if should_allow_trade(z, curve, trend, parameters)
        and z.score >= parameters.min_setup_score
    ]
    
    # 6. Generate trades using PositionManager
    trades = []
    for zone in allowed_zones:
        plan = build_trade_plan(zone, opposing_zone=None, 
                                account_size=position_manager.get_current_cash(),
                                params=parameters)
        
        if plan and plan.planned_r >= parameters.min_reward_risk:
            # Use upstream position manager
            if zone.zone_type == ZoneType.DEMAND:
                trades += position_manager.open_spot(
                    pair=input.strategy_universe.get_single_pair(),
                    value=plan.position_size,
                    stop_loss=plan.stop_loss,
                    take_profit=plan.take_profit,
                )
            else:  # SUPPLY
                trades += position_manager.open_short(
                    pair=input.strategy_universe.get_single_pair(),
                    value=plan.position_size,
                    stop_loss=plan.stop_loss,
                    take_profit=plan.take_profit,
                )
    
    return trades
```

#### Step 1.3: Create Example Notebook

**New file**: `notebooks/supply_demand/supply_demand_v1_upstream.ipynb`

**Cells**:
1. Setup and imports
2. Parameters configuration
3. Create indicators (if needed)
4. Import `decide_trades_sd_v1`
5. Run backtest:
   ```python
   from tradeexecutor.backtest.backtest_runner import run_backtest_inline
   from strategies.supply_demand_v1.decide_trades_adapter import decide_trades_sd_v1
   
   result = run_backtest_inline(
       name="Supply & Demand V1",
       engine_version="0.5",
       decide_trades=decide_trades_sd_v1,
       client=client,
       universe=strategy_universe,
       parameters=parameters,
   )
   ```
6. Display results using upstream analytics

#### Step 1.4: Refactor CSV Runner

**Rename**: `runner.py` → `csv_backtest_adapter.py`

**Changes**:
- Import from `strategy_core.py` instead of duplicating
- Keep order/position management (for now)
- Keep parallel execution
- Keep artifact generation
- Update documentation to clarify this is "CSV-based backtest adapter"

**Rationale**: CSV runner is **proven and working**. Keep it as-is but make clear it's an adapter, not the only way to use the strategy.

#### Step 1.5: Add Documentation

**New file**: `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md`

**Sections**:
1. **Two Ways to Use S&D Strategy**:
   - Upstream adapter (`decide_trades_sd_v1` + `run_backtest_inline`)
   - CSV adapter (`csv_backtest_adapter.py`)

2. **When to Use Each**:
   - Upstream: Real market data, upstream analytics, community tools
   - CSV: Custom experiments, parallel execution, PR comparisons

3. **Feature Comparison**:
   | Feature | Upstream | CSV Adapter |
   |---------|----------|-------------|
   | Real market data | ✅ | ⚠️ Synthetic |
   | Parallel execution | ❌ | ✅ |
   | Artifact generation | ❌ | ✅ |
   | Integrity checks | ❌ | ✅ |
   | Upstream analytics | ✅ | ❌ |

4. **Migration Path**: How to eventually deprecate CSV adapter if upstream adds needed features

### Phase 2: Deprecate Redundant Code (Future PR)

**When**: After validating upstream adapter works correctly

**Changes**:
- Remove `check_limit_order_fill()` from `strategy.py` (use upstream)
- Remove `manage_trade_plan()` from `strategy.py` (use upstream)
- Remove order lifecycle management from `csv_backtest_adapter.py` (use upstream)
- Keep only genuinely unique logic

**Validation**:
- Run both adapters on same data
- Compare results (trades, PnL, metrics)
- Document any differences

### Phase 3: Futures Support Investigation (Future)

**Research Questions**:
1. Does upstream `trade-executor` support Binance futures?
2. Can we extend `PositionManager` to support futures?
3. Do we need to maintain separate futures handling?

**Outcome**:
- If upstream supports futures: migrate fully
- If not: keep CSV adapter for futures, use upstream for spot

---

## Summary of Recommendation

### ✅ Keep (Preserve Our Work)
- Zone detection logic (DBR/RBD, freshness)
- Multi-timeframe gating (curve + trend)
- Odds enhancer scoring
- CSV-based backtester and artifacts
- Parallel execution infrastructure
- Integrity validation checks

### 🔄 Refactor (Align with Upstream)
- Extract strategy core to framework-agnostic module
- Create upstream adapter (`decide_trades_sd_v1`)
- Rename runner to clarify it's a CSV adapter
- Document dual approach (upstream vs CSV)

### ❌ Deprecate (Eventually Delegate to Framework)
- Order fill simulation (let upstream handle)
- TTL tracking (let upstream handle)
- Position state management (let upstream handle)
- PnL calculation (let upstream handle)
- Trade metrics (let upstream handle)

### 🎯 Benefits
1. **Preserves proven work**: CSV backtester keeps working
2. **Enables ecosystem access**: Can use upstream tools and analytics
3. **Reduces maintenance**: Framework handles fills, TTL, PnL
4. **Future-proof**: Strategy logic is portable
5. **Best of both worlds**: CSV adapter for experiments, upstream for production

---

## Files to Create/Modify (Next PR)

### Create:
- [ ] `strategies/supply_demand_v1/strategy_core.py` - Framework-agnostic strategy logic
- [ ] `strategies/supply_demand_v1/decide_trades_adapter.py` - Upstream-compatible interface
- [ ] `strategies/supply_demand_v1/UPSTREAM_COMPATIBILITY.md` - Documentation
- [ ] `notebooks/supply_demand/supply_demand_v1_upstream.ipynb` - Example using upstream

### Rename:
- [ ] `strategies/supply_demand_v1/runner.py` → `csv_backtest_adapter.py`

### Modify:
- [ ] `strategies/supply_demand_v1/strategy.py` - Remove moved functions, add imports
- [ ] `strategies/supply_demand_v1/README.md` - Document dual approach
- [ ] `tests/test_supply_demand_strategy.py` - Update imports

### Tests:
- [ ] Add tests for `strategy_core.py` functions
- [ ] Add tests for `decide_trades_adapter.py`
- [ ] Validate both adapters produce consistent results

---

**Status**: Ready for review and approval before proceeding with refactoring.

**Next Action**: Review this audit with team and approve approach.
