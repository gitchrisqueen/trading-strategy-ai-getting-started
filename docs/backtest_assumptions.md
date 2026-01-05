# Backtest Assumptions and Implementation Details

**Strategy**: Supply & Demand V1  
**Date**: 2026-01-04  
**Purpose**: Document all assumptions, defaults, and implementation details for backtesting

---

## 1. Execution Timing and Bar Handling

### 1.1 Candle Close Semantics

**Assumption**: All strategy calculations use **closed candle data only**.

- **HTF (4h) candles**: Curve analysis updates only when 4h candle closes
- **ITF (1h) candles**: Trend analysis updates only when 1h candle closes
- **LTF (15m) candles**: Zone detection and entry signals use closed 15m candles
- **Intrabar data**: Only used for fill detection (checking if limit order touched during the bar)

**Rationale**: Prevents look-ahead bias. In live trading, you cannot act on incomplete candle data.

### 1.2 Order Placement Timing

**Assumption**: Orders are placed **after the bar closes** where conditions are met.

**Flow**:
1. Bar N closes
2. Strategy evaluates conditions using Bar N's closed data
3. If conditions met, order is placed
4. Order becomes active starting from Bar N+1
5. Order can fill on Bar N+1 or later (within TTL)

**Example**:
```
Bar 100 closes: price=105, zone proximal=100, score=7.0, all gates pass
→ Order placed at end of Bar 100
→ Order active starting Bar 101
→ Order fills if Bar 101, 102, ... 110 (TTL=10) touches proximal
```

### 1.3 Fill Detection (Intrabar)

**Assumption**: Limit orders fill if price **touches** the limit price during the bar.

**LONG (demand zone) fill logic**:
```python
if candle['low'] <= limit_price:
    # Order fills
    actual_entry = limit_price * (1 + slippage_bps/10000 + fees_bps/10000)
```

**SHORT (supply zone) fill logic**:
```python
if candle['high'] >= limit_price:
    # Order fills
    actual_entry = limit_price * (1 - slippage_bps/10000 - fees_bps/10000)
```

**Rationale**: Conservative assumption - if price touched the level, order would have filled.

### 1.4 Stop Loss and Take Profit Detection

**Assumption**: Exit orders trigger if price touches the level **within the bar**.

**LONG position exits**:
```python
# Stop loss
if candle['low'] <= stop_loss:
    exit_reason = 'STOP_LOSS'
    exit_price = stop_loss

# Take profit
elif candle['high'] >= take_profit:
    exit_reason = 'TARGET'
    exit_price = take_profit
```

**SHORT position exits**:
```python
# Stop loss  
if candle['high'] >= stop_loss:
    exit_reason = 'STOP_LOSS'
    exit_price = stop_loss

# Take profit
elif candle['low'] <= take_profit:
    exit_reason = 'TARGET'
    exit_price = take_profit
```

**Priority**: Stop loss checked before take profit (conservative).

---

## 2. Time-To-Live (TTL) Behavior

### 2.1 TTL Definition

**Parameter**: `ttl_bars` (default: 10)

**Meaning**: Number of bars an unfilled limit order remains active before expiration.

### 2.2 TTL Calculation

```python
order_placed_at_idx = 100
expiry_idx = order_placed_at_idx + ttl_bars  # 110
```

**Order expires**: At the END of bar with index `expiry_idx`, or when reaching bar `expiry_idx + 1`.

### 2.3 TTL Expiry Logic

```python
# Check on each bar
if current_idx >= order.expiry_idx and order.status == 'PLACED':
    order.status = 'EXPIRED'
    order.cancel_reason = 'TTL_EXPIRED'
```

### 2.4 TTL Edge Cases

**Case 1: TTL = None**
- Order never expires (remains active indefinitely)
- Not recommended for production

**Case 2: TTL = 0**
- Order expires immediately (same bar placement)
- Effectively disables limit orders

**Case 3: Fill on expiry bar**
- If price touches limit on expiry bar, order still fills
- Expiry only applies to unfilled orders

---

## 3. Trading Costs

### 3.1 Fees

**Parameter**: `fees_bps` (default: 10.0)

**Meaning**: Trading fees in basis points (1 bps = 0.01%)

**Default**: 10 bps = 0.10% per trade

**Application**:
- Applied on ENTRY and EXIT
- Increases cost basis for LONG
- Increases credit for SHORT

**Formula**:
```python
entry_cost_pct = (fees_bps + slippage_bps) / 10000
actual_entry = limit_price * (1 + entry_cost_pct)  # LONG
actual_entry = limit_price * (1 - entry_cost_pct)  # SHORT
```

### 3.2 Slippage

**Parameter**: `slippage_bps` (default: 5.0)

**Meaning**: Expected price slippage in basis points

**Default**: 5 bps = 0.05% per trade

**Rationale**: Accounts for spread, market impact, and execution uncertainty.

### 3.3 Spread

**Assumption**: Spread is **included in slippage**.

No separate spread parameter. The `slippage_bps` accounts for:
- Bid-ask spread
- Market depth
- Execution time
- Price movement during order execution

### 3.4 Zero-Cost Backtests

**Configuration**:
```yaml
fees_bps: 0.0
slippage_bps: 0.0
```

**Use case**: Testing strategy logic without transaction cost impact.

**Note**: Real trading will have costs. Zero-cost backtests are overly optimistic.

---

## 4. Position Sizing and Risk

### 4.1 Risk Definition

**Formula**:
```python
risk = abs(entry_price - stop_loss)
```

**Units**: Price units (e.g., USD for BTC/USDT)

### 4.2 Position Size Calculation

**2% Rule** (default):
```python
risk_pct = 0.02  # 2% of account
account_size = 10000  # USD
entry_price = 100
stop_loss = 95

risk_per_unit = abs(entry_price - stop_loss)  # 5 USD
risk_amount = account_size * risk_pct  # 200 USD
position_size = risk_amount / risk_per_unit  # 40 units
```

**Result**: If stopped out, lose exactly 2% of account (before fees/slippage).

### 4.3 R-Multiple Accounting

**Planned R**: Expected reward-to-risk at entry
```python
reward = abs(target_price - entry_price)
risk = abs(entry_price - stop_loss)
planned_r = reward / risk  # Must be >= 3.0
```

**Realized R**: Actual outcome relative to initial risk
```python
# Full profit
if exit_reason == 'TARGET':
    realized_r = planned_r  # +3.0R

# Full loss
elif exit_reason == 'STOP_LOSS':
    realized_r = -1.0R

# Partial profit (breakeven moved)
elif exit_reason == 'BREAKEVEN':
    realized_r = 0.0R  # Break even

# End-of-data close
elif exit_reason == 'EOD_CLOSE':
    pnl = exit_price - entry_price  # LONG
    realized_r = pnl / risk_per_unit  # Fractional R
```

### 4.4 Breakeven and Trailing

**Breakeven Move**: At `breakeven_at_r` (default 2.0)
```python
if current_profit >= 2.0 * risk:
    stop_loss = entry_price  # Move to breakeven
```

**Take Profit**: At `take_profit_at_r` (default 3.0)
```python
if current_profit >= 3.0 * risk:
    close_position()  # Exit at target
```

---

## 5. Multi-Timeframe Signal Updates

### 5.1 HTF Curve State

**Update frequency**: Every HTF candle close (every 4h)

**Calculation**:
1. Wait for 4h candle to close
2. Identify nearest fresh supply above price
3. Identify nearest fresh demand below price
4. Calculate curve position: LOW, EQUILIBRIUM, HIGH
5. Use this state for next 4h period

**Propagation**: HTF state remains constant between 4h candle closes.

### 5.2 ITF Trend State

**Update frequency**: Every ITF candle close (every 1h)

**Calculation**:
1. Wait for 1h candle to close
2. Detect pivot highs/lows (last `pivot_len` candles)
3. Analyze last `pivots_to_consider` pivots
4. Classify as UP (HH/HL), DOWN (LH/LL), or SIDEWAYS
5. Use this state for next 1h period

**Propagation**: ITF state remains constant between 1h candle closes.

### 5.3 LTF Zone Detection

**Update frequency**: Every LTF candle close (every 15m)

**Process**:
1. New 15m candle closes
2. Check if DBR/RBD pattern completes
3. If zone detected, mark with current index
4. Zone becomes active for consideration

**Freshness tracking**: Updates every 15m as price interacts with zones.

### 5.4 Time Synchronization

**Critical**: HTF and ITF states must be "stale" relative to LTF.

**Example timeline**:
```
00:00 - HTF closes (4h), ITF closes (1h), LTF closes (15m)
        → All signals update
00:15 - LTF closes → Only LTF updates (HTF/ITF unchanged)
00:30 - LTF closes → Only LTF updates
00:45 - LTF closes → Only LTF updates
01:00 - ITF closes (1h), LTF closes (15m)
        → ITF and LTF update (HTF unchanged)
...
04:00 - HTF closes (4h), ITF closes (1h), LTF closes (15m)
        → All signals update
```

**Enforcement**: Implementation must not use "future" HTF/ITF data within their respective periods.

---

## 6. Zone Freshness and Touch Counting

### 6.1 Freshness Definition

**Fresh zone**: Price has NOT returned to zone since creation.

**Technical definition**:
```python
zone_interval = [min(proximal, distal), max(proximal, distal)]

for each subsequent candle:
    if candle['low'] <= zone_interval[1] and candle['high'] >= zone_interval[0]:
        # Zone touched
        zone.freshness_touches += 1
        zone.is_fresh = False
```

### 6.2 Touch Count Scoring

**Freshness score**:
```python
if freshness_touches == 0:
    score = 3.0  # Best - fresh
elif freshness_touches == 1:
    score = 1.5  # Good - one test
else:
    score = 0.0  # Poor - multiple tests
```

### 6.3 Time-Relative Freshness

**Key concept**: A zone can be "fresh at time T" but "not fresh at time T+N".

**Implementation**:
- `zone.is_fresh` is deprecated (final state only)
- Use `is_zone_fresh_at_idx(zone, current_idx)` for time-relative checks
- Precomputed freshness table for performance

---

## 7. Order Deduplication and Retry Logic

### 7.1 One Order Per Zone Rule

**Assumption**: Maximum one active order per zone at any time.

**Enforcement**:
```python
active_orders_by_zone = {(zone_id, side): order_id}

if (zone_id, side) in active_orders_by_zone:
    continue  # Skip - already have active order for this zone
```

### 7.2 Retry Logic

**Parameter**: `max_retries_per_zone` (default: 1)

**Meaning**: Maximum number of times to place order for same zone.

**Count**:
```python
order_history_by_zone = {zone_id: [order1, order2, ...]}

if len(order_history_by_zone[zone_id]) >= max_retries_per_zone:
    continue  # Max retries reached
```

### 7.3 Rearm Logic

**Parameter**: `rearm_requires_price_reset` (default: True)

**Requirement**: After order expires, price must move away from zone before retry.

**Reset condition**:
```python
# For demand zone
price_reset = current_price > (proximal + buffer)

# For supply zone  
price_reset = current_price < (proximal - buffer)
```

**Buffer**: `rearm_price_buffer_pct` (default: 0.005 = 0.5%)

---

## 8. Proximity Trigger (Post-PR#31)

### 8.1 Purpose

Prevent placing orders immediately after zone creation when price is far from zone.

### 8.2 Zone Age Check

**Minimum age**: 5 bars after zone creation

```python
zone_age = current_idx - zone.created_at
if zone_age < 5:
    continue  # Zone too young
```

**Rationale**: Gives zone time to "cool off" before considering for entry.

### 8.3 Distance Check

**Parameter**: `entry_proximity_zone_width_mult` (default: 0.5)

**Formula**:
```python
zone_width = abs(zone.distal - zone.proximal)
distance_to_entry = abs(current_price - limit_price)
proximity_threshold = entry_proximity_zone_width_mult * zone_width

if distance_to_entry > proximity_threshold:
    continue  # Price too far from zone
```

**Interpretation**: Place order only when price within 0.5x zone width.

### 8.4 Price Side Check

**Parameter**: `require_price_on_correct_side` (default: True)

**Logic**:
```python
# For DEMAND (LONG)
if current_price < zone.distal:
    continue  # Price below entire zone

# For SUPPLY (SHORT)
if current_price > zone.distal:
    continue  # Price above entire zone
```

**Rationale**: Price should be approaching zone from outside, not inside it.

---

## 9. Determinism and Reproducibility

### 9.1 Determinism Requirements

**Guarantee**: Same inputs → same outputs (always).

**Requirements**:
- No randomness (or fixed seed if using random data)
- No time-dependent functions (datetime.now())
- No external API calls during backtest
- Fixed parameter sets
- Ordered data processing

### 9.2 Reproducibility

**Artifacts for reproducibility**:
- `run_manifest.json`: Git commit hash, config file, Python version, timestamp
- `summary.json`: Aggregate metrics
- `orders.csv`: All orders with complete lifecycle
- `trades.csv`: All trades with entry/exit details
- `zones.csv`: All detected zones
- `decision_funnel.json`: Step-by-step rejection reasons

**Validation**: Run same config twice → identical artifacts.

---

## 10. Integrity Checks

### 10.1 Look-Ahead Bias Check

**Rule**: Entry must occur AFTER zone creation.

```python
if trade.entry_idx <= zone.legout_end_idx:
    violation = "LOOK_AHEAD_BIAS"
```

### 10.2 R-Multiple Accuracy

**Rule**: Actual R calculation must match planned R at entry.

```python
planned_r = trade.planned_r
calculated_r = abs(target - entry) / abs(entry - stop)

if abs(planned_r - calculated_r) > 0.01:
    violation = "R_CALCULATION_ERROR"
```

### 10.3 Minimum R Enforcement

**Rule**: All trades must have planned_r >= min_reward_risk (default 3.0).

```python
if trade.planned_r < params.min_reward_risk:
    violation = "MIN_R_VIOLATION"
```

### 10.4 Entry Timing

**Rule**: Order placement must respect zone age and proximity.

```python
if order.placed_idx - zone.created_at < min_zone_age:
    violation = "ENTRY_TIMING_VIOLATION"
```

---

## 11. Default Parameter Values

### 11.1 Strategy Parameters

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `min_base_candles` | 1 | candles | Minimum base length for zone |
| `max_base_candles` | 6 | candles | Maximum base length for zone |
| `min_legout_candles` | 1 | candles | Minimum leg-out length |
| `proximal_mode` | "body" | - | Proximal placement: "body" or "wick" |
| `min_setup_score` | 6.0 | points | Minimum odds enhancer score |
| `min_reward_risk` | 3.0 | R | Minimum reward-to-risk ratio |
| `risk_pct` | 0.02 | fraction | Risk per trade (2% of account) |
| `breakeven_at_r` | 2.0 | R | Move stop to BE at 2R profit |
| `take_profit_at_r` | 3.0 | R | Close position at 3R profit |
| `stop_buffer_pct` | 0.001 | fraction | Stop placement buffer (0.1%) |

### 11.2 Multi-Timeframe Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `htf_tf` | "4h" | Higher timeframe for curve |
| `itf_tf` | "1h" | Intermediate timeframe for trend |
| `ltf_tf` | "15m" | Lower timeframe for zones/entry |
| `rtf_tf` | "5m" | Refining timeframe (optional) |
| `pivot_len` | 5 | Lookback for pivot detection |
| `pivots_to_consider` | 4 | Number of pivots for trend |

### 11.3 Cost Parameters

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `fees_bps` | 10.0 | bps | Trading fees (0.10%) |
| `slippage_bps` | 5.0 | bps | Slippage (0.05%) |

### 11.4 Order Management Parameters

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `entry_mode` | "LIMIT" | - | Entry type: LIMIT or CONFIRMATION |
| `ttl_bars` | 10 | bars | Order time-to-live |
| `max_retries_per_zone` | 1 | count | Max order attempts per zone |
| `rearm_requires_price_reset` | True | bool | Require price reset before retry |
| `rearm_price_buffer_pct` | 0.005 | fraction | Price reset buffer (0.5%) |

### 11.5 Proximity Trigger Parameters (Post-PR#31)

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `entry_proximity_zone_width_mult` | 0.5 | multiplier | Place within 0.5x zone width |
| `entry_proximity_abs` | 0.0 | price | Absolute proximity threshold |
| `require_price_on_correct_side` | True | bool | Price must approach from outside |

---

## 12. Data Requirements

### 12.1 Candle Data Format

**Required fields**:
- `open`: Opening price
- `high`: Highest price
- `low`: Lowest price
- `close`: Closing price
- `timestamp` (optional): Candle start time

**Data type**: Float (price), datetime (timestamp)

**Ordering**: Chronological (oldest to newest)

### 12.2 Missing Data Handling

**Assumption**: Data is complete with no gaps.

**If gap exists**: Backtest may produce incorrect results or errors.

**Recommendation**: Validate data continuity before running backtest.

### 12.3 Data Source

**Supported**:
- CSV files with OHLC data
- Synthetic candles (for testing)
- Trading Strategy SDK data (when integrated)

**Not supported**:
- Tick data
- Order book data
- Level 2 data

---

## 13. Limitations and Known Issues

### 13.1 Backtest vs Live Trading Differences

| Aspect | Backtest | Live Trading |
|--------|----------|--------------|
| Fills | Guaranteed if touched | May not fill (liquidity) |
| Slippage | Fixed percentage | Variable |
| Fees | Fixed percentage | Tiered (volume-based) |
| Latency | None | Network + exchange delays |
| Partial fills | Not modeled | Possible |
| Requotes | Not modeled | Possible |

### 13.2 Optimistic Assumptions

**Fills**: Assumes order fills if price touches level. Reality: may not fill due to:
- Insufficient liquidity at level
- Order book depth
- Fast-moving market

**Stop losses**: Assumes fills at exact stop level. Reality:
- Slippage during volatile moves
- Gaps (especially crypto on weekends)

**Recommendation**: Add safety margin to slippage parameter for conservative estimates.

### 13.3 Not Modeled

- **Funding rates** (for perpetual contracts)
- **Rollover costs** (for futures)
- **Margin requirements**
- **Liquidation risk**
- **Exchange outages**
- **Network congestion**
- **API rate limits**

---

## 14. Change Log

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-04 | @copilot | Initial backtest assumptions documentation |

