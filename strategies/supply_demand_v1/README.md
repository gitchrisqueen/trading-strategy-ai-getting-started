# Supply & Demand V1 Trading Strategy

## Overview

The Supply & Demand (S&D) V1 strategy is a zone-based trading approach that identifies institutional supply and demand areas through price action patterns, then trades retracements back into these zones.

**Core Premise**: Large institutions (market makers, banks, hedge funds) leave footprints in the form of price patterns. By identifying where they accumulated or distributed positions, we can trade when price returns to these areas.

## Intended Market: Futures/Perpetual Contracts

**This strategy is designed for futures and perpetual contract markets.**

The strategy assumes:
- **Bidirectional trading capability**: Ability to go both LONG (buy) and SHORT (sell) with equal ease
- **Sufficient volatility**: Markets with enough price movement to form clear supply/demand zones
- **Leverage availability**: Ability to size positions appropriately using leverage (though conservative position sizing is recommended)
- **High liquidity**: Tight spreads and minimal slippage on entry/exit

### Not Intended for Spot-Only Markets

This strategy is **not optimized** for spot-only trading environments where:
- Short selling is restricted or unavailable
- Markets lack sufficient volatility for zone formation
- Trading costs prohibit frequent entries/exits
- Leverage is not available for position sizing

For best results, apply this strategy to liquid futures/perpetual pairs on exchanges like Binance Futures, Bybit, OKX, or similar derivative platforms.

## Key Terminology

| Term | Definition |
|------|------------|
| **Supply Zone** | Price area where selling pressure historically overwhelmed buying (Rally-Base-Drop pattern) |
| **Demand Zone** | Price area where buying pressure historically overwhelmed selling (Drop-Base-Rally pattern) |
| **Proximal Line** | Zone boundary closest to current price (entry reference) |
| **Distal Line** | Zone boundary farthest from current price (stop reference) |
| **Fresh Zone** | Zone that price has not revisited since creation |
| **Base** | Consolidation period of boring candles (supply/demand balance) |
| **Leg-Out** | Strong momentum move away from base (exciting candles) |
| **Boring Candle** | Candle with body ≤ 50% of range (consolidation) |
| **Exciting Candle** | Candle with body > 50% of range (momentum) |
| **Curve** | HTF context - is price HIGH, LOW, or EQUILIBRIUM? |
| **Trend** | ITF context - is price moving UP, DOWN, or SIDEWAYS? |
| **R (Risk Multiple)** | Reward divided by risk (e.g., 3R = 3:1 reward-to-risk) |
| **SET** | Stop, Entry, Target (complete trade plan) |

## Candle Classification

All zone logic depends on classifying candles as "boring" or "exciting".

### Body and Range

```
body = |close - open|
range = high - low
```

### Boring Candle (Consolidation)

**Rule**: `body <= 0.50 * range`

**Interpretation**: Supply and demand are balanced. Institutions may be accumulating orders without moving price.

**Example**:
```
Open: 100, Close: 101, High: 103, Low: 99
body = |101 - 100| = 1
range = 103 - 99 = 4
ratio = 1 / 4 = 0.25 (25%)
Result: BORING (25% ≤ 50%)
```

### Exciting Candle (Momentum)

**Rule**: `body > 0.50 * range`

**Interpretation**: Strong imbalance. One side overwhelms the other. Institutions are less active inside this candle—they finished accumulating before the move.

**Example**:
```
Open: 100, Close: 103, High: 104, Low: 100
body = |103 - 100| = 3
range = 104 - 100 = 4
ratio = 3 / 4 = 0.75 (75%)
Result: EXCITING (75% > 50%)
```

### Edge Case: Doji

If `range = 0` (open = high = low = close), classify as **boring**.

## Zone Patterns

### Drop-Base-Rally (DBR) - Demand Zone

**Pattern**: Price **drops** (leg-in) → forms a **base** → **rallies** strongly (leg-out)

**Structure**:
1. **Leg-In**: One or more exciting DOWN candles
2. **Base**: 1-6 boring candles
3. **Leg-Out**: One or more exciting UP candles

**Trade Logic**: When price returns to this zone, institutional buyers may be waiting. Enter LONG.

**Example**:
```
Candle 0: Open=110, Close=100, High=110, Low=100  [Exciting drop, 100% body ratio]
Candle 1: Open=100, Close=101, High=102, Low=99   [Boring base, 33% body ratio]
Candle 2: Open=101, Close=100, High=102, Low=99   [Boring base, 33% body ratio]
Candle 3: Open=100, Close=110, High=110, Low=100  [Exciting rally, 100% body ratio]

Result: DBR demand zone detected
```

### Rally-Base-Drop (RBD) - Supply Zone

**Pattern**: Price **rallies** (leg-in) → forms a **base** → **drops** strongly (leg-out)

**Structure**:
1. **Leg-In**: One or more exciting UP candles
2. **Base**: 1-6 boring candles
3. **Leg-Out**: One or more exciting DOWN candles

**Trade Logic**: When price returns to this zone, institutional sellers may be waiting. Enter SHORT.

**Example**:
```
Candle 0: Open=100, Close=110, High=110, Low=100  [Exciting rally]
Candle 1: Open=110, Close=111, High=112, Low=109  [Boring base]
Candle 2: Open=111, Close=110, High=112, Low=109  [Boring base]
Candle 3: Open=110, Close=100, High=110, Low=100  [Exciting drop]

Result: RBD supply zone detected
```

## Zone Boundaries: Proximal and Distal Lines

Every zone has two horizontal lines defining its range:

### Demand Zone (DBR) Lines

**Proximal** (entry reference):
- Draw at the **highest candle body** within the base
- For bullish candles: top of body (close)
- For bearish candles: top of body (open)
- Implementation: `max(max(open, close) for candle in base_candles)`

**Distal** (stop reference):
- Draw at the **lowest wick** across entire DBR structure (leg-in + base + leg-out)
- Implementation: `min(low for candle in entire_structure)`

### Supply Zone (RBD) Lines

**Proximal** (entry reference):
- Draw at the **lowest candle body** within the base
- For bullish candles: bottom of body (open)
- For bearish candles: bottom of body (close)
- Implementation: `min(min(open, close) for candle in base_candles)`

**Distal** (stop reference):
- Draw at the **highest wick** across entire RBD structure (leg-in + base + leg-out)
- Implementation: `max(high for candle in entire_structure)`

### Proximal Modes

Two modes for proximal placement (configurable):

1. **Body mode** (default): Use body boundaries as described above
2. **Wick mode**: Use wick extremes (more conservative, wider zones)

Parameter: `proximal_mode = "body"` or `"wick"`

## Zone Freshness

**Fresh zone**: Price has **not returned** to the zone since it was created.

**Not fresh**: Price has revisited the zone at least once.

### Freshness Detection

After a zone is created (at legout_end_idx), track subsequent candles:

**For Demand Zone**:
- Zone is fresh until a candle's `low <= proximal`
- Each time `low <= proximal`, increment `freshness_touches`
- If `freshness_touches > 0`, zone is not fresh

**For Supply Zone**:
- Zone is fresh until a candle's `high >= proximal`
- Each time `high >= proximal`, increment `freshness_touches`
- If `freshness_touches > 0`, zone is not fresh

### Freshness Updates

Freshness is updated dynamically as new candles arrive:

```python
def is_zone_fresh(zone, candles, current_idx):
    """Update zone freshness by checking if price returned"""
    for i in range(zone.created_at + 1, current_idx + 1):
        candle = candles[i]
        if zone.zone_type == ZoneType.DEMAND:
            if candle['low'] <= zone.proximal:
                zone.freshness_touches += 1
                zone.is_fresh = False
        else:  # SUPPLY
            if candle['high'] >= zone.proximal:
                zone.freshness_touches += 1
                zone.is_fresh = False
```

## Multi-Timeframe Framework

The strategy uses **three timeframes** to build context:

| Timeframe | Abbreviation | Purpose | Default (Crypto) |
|-----------|--------------|---------|------------------|
| Higher Time Frame | HTF | Curve analysis (big picture context) | 4H |
| Intermediate Time Frame | ITF | Trend direction | 1H |
| Lower Time Frame | LTF | Zone detection and entry | 15m |
| Refining Time Frame | RTF | Optional refinement | 5m |

### HTF: Curve Analysis

**Question**: Is price high, low, or in equilibrium within the broader range?

**Process**:
1. From current price on HTF, find nearest **fresh supply zone above**
2. Find nearest **fresh demand zone below**
3. Define range: `[demand_proximal, supply_proximal]`
4. Divide range into thirds:
   - **Low**: Bottom third (favor LONG from demand)
   - **Equilibrium**: Middle third (be selective)
   - **High**: Top third (favor SHORT from supply)

**Pseudocode**:
```
curve_range = supply_proximal - demand_proximal
third = curve_range / 3

if current_price < demand_proximal + third:
    curve = LOW
elif current_price > supply_proximal - third:
    curve = HIGH
else:
    curve = EQUILIBRIUM
```

### ITF: Trend Direction

**Question**: Is price trending up, down, or sideways?

**Process**:
1. Detect pivot highs and pivot lows using lookback parameter (`pivot_len`)
2. Analyze last N pivots (`pivots_to_consider`)
3. Classify:
   - **Uptrend**: Higher highs and higher lows (HH/HL)
   - **Downtrend**: Lower highs and lower lows (LH/LL)
   - **Sideways**: Mixed or equal levels

**Pseudocode**:
```
pivots = detect_pivot_highs_lows(candles, pivot_len)
recent_highs = last_N_pivot_highs(pivots, pivots_to_consider)
recent_lows = last_N_pivot_lows(pivots, pivots_to_consider)

if highs_increasing(recent_highs) and lows_increasing(recent_lows):
    trend = UP
elif highs_decreasing(recent_highs) and lows_decreasing(recent_lows):
    trend = DOWN
else:
    trend = SIDEWAYS
```

### LTF: Zone Detection and Entry

Zones are detected on the LTF using the DBR/RBD patterns described earlier.

## Odds Enhancers (Setup Scoring)

Each zone is scored based on **odds enhancers** to rate setup quality.

### 1. Freshness (0 / 1.5 / 3 points)

| Touches | Score | Interpretation |
|---------|-------|----------------|
| 0 (fresh) | 3.0 | Best - price never returned |
| 1 | 1.5 | Good - tested once |
| ≥2 | 0.0 | Poor - multiple tests |

### 2. Leg-Out Strength (0 / 1 / 2 points)

Measures momentum of the breakout from the zone.

**Calculation**:
```
legout_return = |close_legout_end - close_base_end| / close_base_end
```

**Scoring**:
- `legout_return >= 10%` → 2 points (Best)
- `legout_return >= 5%` → 1 point (Good)
- `legout_return < 5%` → 0 points (Poor)

Parameters: `legout_strength_high_threshold`, `legout_strength_mid_threshold`

### 3. Time in Base (0 / 1 / 2 points)

Number of candles in the base period.

| Base Candles | Score | Interpretation |
|--------------|-------|----------------|
| ≤3 | 2.0 | Best - tight consolidation |
| 4-6 | 1.0 | Good - acceptable consolidation |
| >6 | 0.0 | Poor - too much time |

Parameters: `base_time_best`, `base_time_good`

### 4. Profit Zone (0 / 1.5 / 3 points)

Distance to opposing zone (how much profit potential exists).

**Calculation**:
```
For LONG: max_reward = supply_proximal - entry
For SHORT: max_reward = entry - demand_proximal

risk = |entry - stop|
available_R = max_reward / risk
```

**Scoring**:
- `available_R >= 3.0` → 3 points (Best)
- `available_R >= 2.0` → 1.5 points (Good)
- `available_R < 2.0` → 0 points (Poor)

### Total Score and Threshold

**Maximum possible score**: 3 + 2 + 2 + 3 = **10 points**

**Minimum score to trade**: `min_setup_score` (default 6.0)

**Interpretation**:
- Score ≥ 8: Excellent setup
- Score 6-7: Good setup
- Score < 6: Skip (too risky)

## Multi-Timeframe Gating

After scoring, apply additional filters based on **curve** and **trend**:

### Gating Rules

| Zone Type | Curve | Trend | Action |
|-----------|-------|-------|--------|
| DEMAND | LOW | UP or SIDEWAYS | ALLOW |
| DEMAND | LOW | DOWN | BLOCK (trend against) |
| DEMAND | HIGH | any | BLOCK (wrong side of curve) |
| SUPPLY | HIGH | DOWN or SIDEWAYS | ALLOW |
| SUPPLY | HIGH | UP | BLOCK (trend against) |
| SUPPLY | LOW | any | BLOCK (wrong side of curve) |
| DEMAND | EQ | UP | ALLOW (if score high enough) |
| SUPPLY | EQ | DOWN | ALLOW (if score high enough) |
| any | EQ | SIDEWAYS | BLOCK (no directional edge) |

### Equilibrium Handling

When curve is EQUILIBRIUM:
- Require trend alignment (demand + uptrend, or supply + downtrend)
- Require bonus score: `score >= min_setup_score + eq_min_setup_score_bonus`
- Default bonus: 1.0 point

Parameters:
- `allow_eq_trades` (default True)
- `eq_requires_trend_alignment` (default True)
- `eq_min_setup_score_bonus` (default 1.0)

## Entry Types

### 1. Limit Entry (Default)

Place a limit order at the proximal line.

**For LONG (demand zone)**:
- Limit buy at proximal
- Order fills if price touches proximal

**For SHORT (supply zone)**:
- Limit sell at proximal
- Order fills if price touches proximal

**Time-to-live**: Orders expire after `ttl_bars` candles (default 10)

### 2. Confirmation Entry (Optional)

Wait for price to enter the zone and then reverse.

**For LONG**:
- Wait for price to drop into demand zone
- Enter when price crosses **above** proximal (reversal confirmation)

**For SHORT**:
- Wait for price to rally into supply zone
- Enter when price crosses **below** proximal (reversal confirmation)

Parameter: `entry_mode = EntryMode.LIMIT` or `EntryMode.CONFIRMATION`

## Stop Loss Placement

**For LONG**: Stop goes below distal with a buffer
```
stop_loss = distal * (1 - stop_buffer_pct)
```

**For SHORT**: Stop goes above distal with a buffer
```
stop_loss = distal * (1 + stop_buffer_pct)
```

Default buffer: `stop_buffer_pct = 0.001` (0.1%)

**Why buffer?**: Prevents stop from being at exact support/resistance where it might get swept.

## Take Profit and Trade Management

### Exit Detection and Lifecycle

Positions are simulated across multiple bars from entry to exit. On each bar after entry, the backtest engine checks for exit conditions using **intrabar price action** (candle high/low).

#### Exit Reasons

| Exit Reason | Description |
|-------------|-------------|
| **STOP** | Stop loss was hit (long: candle low ≤ stop, short: candle high ≥ stop) |
| **TARGET** | Take profit target was hit (long: candle high ≥ target, short: candle low ≤ target) |
| **EOD_CLOSE** | Position still open at end of data (closed at final candle close) |
| **TTL_CANCEL** | Limit order expired before fill (TTL = Time To Live) |

#### Same-Bar Stop and Target Rule

If both stop and target are hit within the same candle (wide-ranging bar), the backtest uses a **conservative approach**:

**Default Rule**: Assume **STOP hits first**

This is configurable via `stop_wins_on_same_bar` parameter in `check_intrabar_exit()`.

**Rationale**: Conservative position sizing. Better to underestimate wins than overestimate them. In real trading, slippage and market impact make hitting far targets less likely if price initially moved against you.

**Example**:
```
Entry: 100 (LONG)
Stop: 95
Target: 115
Candle: low=90, high=120  (both hit)
Result: Exit at STOP (95) with -1R
```

### Initial Target

Minimum target is **3R** (3x risk).

```
risk = |entry - stop|
target = entry + (3 * risk)  [for LONG]
target = entry - (3 * risk)  [for SHORT]
```

**Constraint**: Target must not extend beyond opposing zone's proximal (exit before competitive buying/selling begins).

### Trade Management Plan #1 (Default)

**At 2R profit**:
- Move stop to **breakeven** (entry price)
- This locks in zero loss

**At 3R profit**:
- **Close position** (take profit)

### Trade Management Plan #2 (Alternative)

**At 1R profit**:
- Move stop to breakeven

**At 2R profit**:
- Close position

Parameters:
- `breakeven_at_r` (default 2.0)
- `take_profit_at_r` (default 3.0)

### Trade Management Pseudocode

```python
def check_intrabar_exit(plan, candle, is_long):
    """Check if stop or target hit on this candle"""
    if is_long:
        stop_hit = candle['low'] <= plan.stop_loss
        target_hit = candle['high'] >= plan.take_profit
    else:
        stop_hit = candle['high'] >= plan.stop_loss
        target_hit = candle['low'] <= plan.take_profit
    
    # Both hit on same bar: stop wins (conservative)
    if stop_hit and target_hit:
        return 'STOP'
    
    if stop_hit:
        return 'STOP'
    if target_hit:
        return 'TARGET'
    
    return None  # No exit, position stays open

def manage_trade_plan(plan, current_price, is_long):
    """Update stop based on profit level (called every bar)"""
    entry = plan.actual_entry_price or plan.entry_price
    stop = plan.stop_loss
    risk = abs(entry - stop)
    
    if is_long:
        current_r = (current_price - entry) / risk
    else:
        current_r = (entry - current_price) / risk
    
    # Check for breakeven move at 2R
    if current_r >= breakeven_at_r:
        if (is_long and stop < entry) or (not is_long and stop > entry):
            plan.stop_loss = entry  # Move to breakeven
    
    return {'update_stop': plan.stop_loss, 'current_r': current_r}
```

**Key Points**:
- Exit detection (`check_intrabar_exit`) is separate from stop management (`manage_trade_plan`)
- Exits are checked using intrabar high/low, not just close price
- Stop management can move stop to breakeven at 2R profit
- Position stays open until stop, target, or end of data

## Position Sizing (2% Rule)

**Rule**: Risk no more than 2% of account per trade.

**Formula**:
```
risk_amount = account_size * risk_pct
risk_per_unit = |entry - stop|
position_size = risk_amount / risk_per_unit
```

**Example**:
```
Account: $10,000
Risk %: 2% (0.02)
Entry: $100
Stop: $98

risk_amount = 10,000 * 0.02 = $200
risk_per_unit = |100 - 98| = $2
position_size = 200 / 2 = 100 units
```

Parameter: `risk_pct` (default 0.02)

## Complete Strategy Workflow

### 1. Zone Detection (LTF)

```
For each candle in history:
    Classify as boring or exciting
    
For each potential zone pattern:
    Check for DBR or RBD structure:
        - Leg-in: exciting move
        - Base: 1-6 boring candles
        - Leg-out: exciting move in opposite direction
    
    If pattern found:
        Compute proximal and distal lines
        Record zone with metadata (created_at, base_len, legout_return, etc.)
        Mark as fresh
```

### 2. Freshness Tracking

```
For each zone:
    For each new candle after zone creation:
        If price touches zone:
            Increment freshness_touches
            Mark as not fresh
```

### 3. Multi-Timeframe Analysis

```
# HTF Curve
Find nearest fresh supply above current_price
Find nearest fresh demand below current_price
Classify curve as LOW, EQUILIBRIUM, or HIGH

# ITF Trend
Detect pivot highs and lows
Analyze recent pivots
Classify trend as UP, DOWN, or SIDEWAYS
```

### 4. Zone Scoring

```
For each zone:
    score = 0
    
    # Freshness
    if freshness_touches == 0: score += 3
    elif freshness_touches == 1: score += 1.5
    
    # Leg-out strength
    if legout_return >= 0.10: score += 2
    elif legout_return >= 0.05: score += 1
    
    # Time in base
    if base_len <= 3: score += 2
    elif base_len <= 6: score += 1
    
    # Profit zone
    available_R = distance_to_opposing_zone / risk
    if available_R >= 3.0: score += 3
    elif available_R >= 2.0: score += 1.5
    
    zone.score = score
```

### 5. Multi-Timeframe Gating

```
For each zone with score >= min_setup_score:
    Apply gating rules based on:
        - Zone type (DEMAND or SUPPLY)
        - Curve location (LOW, EQ, HIGH)
        - Trend direction (UP, DOWN, SIDEWAYS)
    
    If zone passes gating:
        Add to tradeable zones
    Else:
        Skip zone
```

### 6. Trade Plan Generation

```
For each tradeable zone:
    # Entry
    entry_price = zone.proximal
    
    # Stop
    if DEMAND:
        stop_loss = zone.distal * (1 - stop_buffer_pct)
    else:  # SUPPLY
        stop_loss = zone.distal * (1 + stop_buffer_pct)
    
    # Target (minimum 3R, capped at opposing zone)
    risk = |entry_price - stop_loss|
    target_price = entry_price + (min_reward_risk * risk)  [LONG]
    target_price = min(target_price, opposing_zone_proximal)
    
    # Position size
    risk_amount = account_size * risk_pct
    position_size = risk_amount / risk
    
    # Create trade plan
    plan = TradePlan(
        zone=zone,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=target_price,
        position_size=position_size,
        risk_amount=risk_amount,
        score=zone.score
    )
```

### 7. Order Execution (Limit Mode)

```
For each trade plan:
    Place limit order at entry_price
    Track placed_at_idx (current candle index)
    Set order_state = PENDING
    
For each pending order:
    Check if current candle touches entry level:
        If touched:
            Mark order as FILLED
            Record filled_at_idx
            Calculate actual_entry_price (entry + slippage + fees)
            Open position
    
    Check if TTL expired:
        If current_idx - placed_at_idx > ttl_bars:
            Mark order as CANCELLED
            Remove order
```

### 8. Trade Management

```
For each open position:
    Calculate current R:
        current_r = (current_price - entry) / risk  [LONG]
        current_r = (entry - current_price) / risk  [SHORT]
    
    If current_r >= take_profit_at_r:
        Close position (profit target hit)
    
    If current_r >= breakeven_at_r:
        If stop not at breakeven yet:
            Move stop to entry (breakeven)
    
    If current_price hits stop:
        Close position (stop loss hit)
```

## Backtest Integrity Checks

To ensure backtest quality, run these validations:

### 1. Look-Ahead Bias

**Check**: Verify that trading decisions are made **after** zone creation, not before.

```
For each trade:
    decision_time >= zone.created_time
```

### 2. Entry Before Zone

**Check**: Verify that entry occurs **after** the zone was created.

```
For each trade:
    entry_time > zone.created_time
```

### 3. R-Multiple Accuracy

**Check**: Verify that planned R matches actual calculation.

```
For each trade:
    risk = |entry - stop|
    reward = |target - entry|
    calculated_r = reward / risk
    
    Assert: |calculated_r - trade.r_multiple| < tolerance
```

### 4. Minimum R Enforcement

**Check**: Verify that all trades meet minimum R requirement.

```
For each trade:
    Assert: trade.r_multiple >= min_reward_risk
```

## Parameters Reference

### Candle Classification
- `boring_body_ratio`: 0.50 (body ≤ 50% of range)
- `exciting_body_ratio`: 0.50 (body > 50% of range)

### Zone Detection
- `min_base_candles`: 1
- `max_base_candles`: 6
- `min_legout_candles`: 1
- `proximal_mode`: "body" or "wick"

### Scoring Thresholds
- `min_setup_score`: 6.0
- `freshness_touches_best`: 0
- `freshness_touches_good`: 1
- `base_time_best`: 3
- `base_time_good`: 6
- `legout_strength_high_threshold`: 0.10 (10%)
- `legout_strength_mid_threshold`: 0.05 (5%)

### Trade Management
- `risk_pct`: 0.02 (2%)
- `breakeven_at_r`: 2.0
- `take_profit_at_r`: 3.0
- `min_reward_risk`: 3.0
- `stop_buffer_pct`: 0.001 (0.1%)

### Multi-Timeframe
- `htf_tf`: "4h"
- `itf_tf`: "1h"
- `ltf_tf`: "15m"
- `rtf_tf`: "5m" (optional)

### Trend Detection
- `pivot_len`: 5
- `pivots_to_consider`: 4

### Gating
- `allow_eq_trades`: True
- `eq_requires_trend_alignment`: True
- `eq_min_setup_score_bonus`: 1.0

### Entry
- `entry_mode`: EntryMode.LIMIT
- `ttl_bars`: 10 (limit order expiry)

### Trading Costs
- `fees_bps`: 10.0 (0.1%)
- `slippage_bps`: 5.0 (0.05%)

## Strategy Strengths

1. **Objective rules**: No discretion needed—all decisions are algorithmic
2. **Multi-timeframe alignment**: Trades with broader market context
3. **Risk-first approach**: Always defines stop loss before entry
4. **Asymmetric risk/reward**: Minimum 3:1 R:R ensures profitability even with <50% win rate
5. **Fresh zones prioritized**: Focuses on untested levels with highest probability
6. **Adaptive trade management**: Moves stop to breakeven to protect profits

## Strategy Limitations

1. **Requires trending markets**: Poor performance in choppy, range-bound markets
2. **Lag in reversals**: May enter counter-trend if HTF context shifts
3. **Fixed R targets**: Doesn't account for volatility changes
4. **Zone subjectivity**: Base identification can vary slightly in edge cases
5. **Slippage sensitive**: Tight stops can lead to premature exit in volatile markets

## How to Run Experiments

The strategy includes a dedicated experiment runner for repeatable backtests across multiple symbols and time ranges. This generates machine-readable artifacts for comparing runs between PRs.

### Quick Start

Run a backtest experiment using the CLI:

```bash
# Run default experiment (5 symbols)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Run wide symbols experiment (15 symbols)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml
```

### Configuration Files

Experiment configurations are stored in `./experiments/`:

- `sd_v1_default.yaml` - Basic configuration with 5 symbols for quick testing
- `sd_v1_wide_symbols.yaml` - Comprehensive configuration with 15 symbols

Each configuration includes:
- **Symbols**: List of trading pairs to backtest
- **Time Range**: Start and end dates
- **Timeframes**: HTF/ITF/LTF settings
- **Scoring**: Odds enhancer thresholds and minimum setup score
- **Trade Management**: Risk %, R multiples, stop/target settings
- **Costs**: Trading fees and slippage in basis points
- **Data Generation**: Parameters for synthetic candle generation

### Output Artifacts

Each run creates a timestamped folder in `./artifacts/sd_v1/<timestamp>_<short_hash>/` containing:

| File | Description |
|------|-------------|
| **summary.json** | Aggregate metrics + per-symbol breakdown |
| **trades.csv** | All trades with: symbol, side, entry, stop, target, planned_R, realized_R, entry_idx, exit_idx, entry_time, exit_time, exit_reason (STOP/TARGET/EOD_CLOSE), score, curve_state, trend_state, pnl, position_size |
| **zones.csv** | All detected zones with: zone_type, proximal, distal, created_at, touches, score inputs |
| **run_manifest.json** | Git commit hash, config used, Python version, timestamp |
| **violations.json** | Integrity check results: planned_R violations, entry timing issues, look-ahead flags |

### Programmatic Usage

You can also use the runner directly in Python:

```python
from strategies.supply_demand_v1.runner import run_backtest_experiment, write_artifacts, create_artifacts_folder

# Run experiment
result = run_backtest_experiment("experiments/sd_v1_default.yaml")

# Access results
print(f"Total trades: {result.aggregate_metrics['total_trades']}")
print(f"Win rate: {result.aggregate_metrics['overall_win_rate']:.2%}")

# Write artifacts
artifacts_dir = create_artifacts_folder()
write_artifacts(result, artifacts_dir)
```

### Integrity Checks

The runner automatically validates backtest integrity by checking for:

1. **Minimum R Enforcement**: Flags any trade with `planned_R < min_reward_risk`
2. **Entry Timing**: Ensures entries occur after zone creation (no look-ahead bias)
3. **R Calculation Consistency**: Validates R = abs(target-entry)/abs(entry-stop)

Violations are reported in `violations.json` for debugging.

### Creating Custom Experiments

To create a new experiment configuration:

1. Copy an existing config: `cp experiments/sd_v1_default.yaml experiments/my_experiment.yaml`
2. Edit parameters as needed (symbols, dates, scoring thresholds, etc.)
3. Run: `python scripts/run_supply_demand_v1.py --config experiments/my_experiment.yaml`

### Comparing Runs Between PRs

Use the artifacts to compare strategy changes:

```bash
# Before PR
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Artifacts: artifacts/sd_v1/20241231_120000_abc12345/

# After PR (with changes)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
# Artifacts: artifacts/sd_v1/20241231_130000_def67890/

# Compare summary.json files to see impact of changes
```

This deterministic output allows you to measure the impact of code changes on strategy performance.

## Implementation Notes

The strategy is implemented in `strategies/supply_demand_v1/strategy.py` with:
- All logic deterministic and testable
- No external dependencies beyond pandas/numpy
- Comprehensive test coverage in `tests/test_supply_demand_*.py`
- Documented in `strategies/supply_demand_v1/TradingStrategySpec.md`

See `notebooks/supply_demand/supply_demand_v1_backtest.ipynb` for a complete working example.
