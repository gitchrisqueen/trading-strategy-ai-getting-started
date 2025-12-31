# Supply and Demand Trading Strategy (Text-Only Spec)

> Purpose: Convert the original image-heavy TradingStrategyDoc into a complete, implementation-ready, text-only specification.

---

## 1. Core Concepts and Terms

- **Supply (S):** A price area where selling pressure historically overwhelms buying pressure.
- **Demand (D):** A price area where buying pressure historically overwhelms selling pressure.
- **Bullish:** Bias toward higher prices (uptrend).
- **Bearish:** Bias toward lower prices (downtrend).
- **SET (Stop, Entry, Target):** Every trade must define Stop Loss, Entry, and Profit Target.
- **Entry:** Opening a position.
- **Exit:** Closing a position for profit or loss.
- **Stop Loss:** Protective exit order that caps loss.
- **Target:** Profit-taking exit order.
- **Risk:** `abs(entry - stop)`
- **Reward:** `abs(target - entry)`
- **Reward-to-Risk (R:R):** `reward / risk`. As a beginner, do not take trades with less than **3:1** (3R).
- **Long:** Profit from price rising.
- **Short:** Profit from price falling (common in futures/forex).

---

## 2. Candles. “Boring” vs “Exciting”

All zone logic is built on candle-body vs range:

- **Body:** `abs(close - open)`
- **Range:** `high - low`

### 2.1 Boring Candle (Base Candidate)
A “boring” candle implies supply and demand are temporarily balanced and institutions may be accumulating orders.

- **Rule:** `body <= 0.50 * range`

### 2.2 Exciting Candle (Leg-In or Leg-Out Candidate)
An “exciting” candle implies strong imbalance. Institutions are less active *inside* the body. The origin of a series of exciting candles is where imbalance is highest.

- **Rule:** `body > 0.50 * range`

### 2.3 Zone Structure
All supply/demand zones are made of **3 elements**, left-to-right on the chart:

1. **Leg-In:** An exciting move *into* the base (can be rally or drop).
2. **Base:** One or more boring candles (can be 1+ candles).
3. **Leg-Out:** A sequence of exciting candles leaving the base.

---

## 3. Two Core Setups

### 3.1 Demand Setup. Drop-Base-Rally (DBR)
- **Pattern:** Price **drops**, forms a **base**, then **rallies** strongly.
- **Trade action:** **Buy retracement** back into the demand zone.

### 3.2 Supply Setup. Rally-Base-Drop (RBD)
- **Pattern:** Price **rallies**, forms a **base**, then **drops** strongly.
- **Trade action:** **Sell retracement** back into the supply zone.

---

## 4. Zones. Proximal and Distal Lines

A **Zone** is a region on the chart bounded by two horizontal lines:

- **Proximal line:** The boundary **closest** to current price (entry reference).
- **Distal line:** The boundary **farthest** from current price (stop reference).

### 4.1 Demand Zone Line Placement (DBR)
- **Proximal line:** Draw at the **highest candle body** within the base (top of body of the highest-bodied candle in the base).
- **Distal line:** Draw at the **lowest wick** (lowest low) across the whole Drop-Base-Rally structure.
- **Stop reference:** Stop goes just **below distal**.

### 4.2 Supply Zone Line Placement (RBD)
- Mirror of demand:
- **Proximal line:** Draw at the **lowest candle body** within the base (bottom of body of the lowest-bodied candle in the base).
- **Distal line:** Draw at the **highest wick** (highest high) across the whole Rally-Base-Drop structure.
- **Stop reference:** Stop goes just **above distal**.

### 4.3 Where Proximal Line May Be Drawn (Manual Flexibility)
The original material notes proximal can be placed at:
1. Top of the candle stick (near wick top),
2. Top of candle body,
3. Bottom of candle body.

**Implementation decision:** Use the **candle body boundary** that aligns with the “closest-to-current-price” boundary as described above for DBR/RBD, and expose a parameter allowing:
- `proximal_mode = "body"` (default),
- `proximal_mode = "wick"` (more conservative entry).

### 4.4 Fresh vs Not Fresh
- **Fresh level:** Price has **not returned** to (or pierced) the level since it was created.
- **Not fresh:** Price has returned, traded into, or pierced the level after creation.

**Implementation decision:** Define “freshness” as:
- A zone is **fresh** until any subsequent candle’s high/low overlaps the zone interval `[distal, proximal]` (for demand) or `[proximal, distal]` (for supply).

---

## 5. Multi-Timeframe Framework

A minimum of **three timeframes** are used:

1. **HTF. Higher Time Frame:** Used to assess the **Curve** (where price is in the big picture).
2. **ITF. Intermediate Time Frame:** Used to assess **Trend** (up/down/sideways).
3. **LTF. Lower Time Frame:** Used to identify zones and **SET** entries.
4. **RTF (optional). Refining Time Frame:** Used to refine proximal/distal.

### 5.1 Practical Defaults (Implementation Choice)
To make this implementable and backtestable immediately:

- **Crypto (default):**
  - HTF: 4H
  - ITF: 1H
  - LTF: 15m
  - RTF: 5m (optional)

Expose as parameters so you can change for stocks or futures later.

---

## 6. Curve Analysis (HTF)

Curve analysis answers: **Are we high, low, or in equilibrium in the curve?**

Steps:
1. Starting at **current price** on HTF.
2. Identify the **nearest fresh supply zone above** price.
3. Identify the **nearest fresh demand zone below** price.
4. Use their proximal lines to define a range.
5. Split the range into **three equal sections** (“thirds”):
   - **High in the curve** (top third),
   - **Equilibrium** (middle third),
   - **Low in the curve** (bottom third).

**Implementation decision:** Use the distance between:
- Supply proximal (upper bound) and Demand proximal (lower bound),
then compute thirds.

---

## 7. Trend Analysis (ITF)

Trend is the direction price is moving between larger-timeframe supply and demand.

Manual concept:
- **Uptrend:** Higher highs and higher lows (HH/HL)
- **Downtrend:** Lower highs and lower lows (LH/LL)
- **Sideways:** Relatively equal highs and lows

**Implementation decision:** Use a pivot-based trend detector:
- Detect pivot highs/lows (lookback parameter `pivot_len`).
- Classify last N pivots for HH/HL vs LH/LL.

---

## 8. Decision Matrix. What to Do When

The strategy combines:
- Current **S&D type** (supply or demand on LTF),
- **Trend** (ITF),
- **Curve location** (HTF),

to decide action:

General guidance encoded from the original matrix:
- **High in curve:** favor **shorts** from supply. Prefer waiting on demand.
- **Low in curve:** favor **longs** from demand. Prefer waiting on supply.
- **Equilibrium:** be more selective. Prefer alignment with trend and strongest zones.

**Implementation decision:** Convert to a simple scoring system:
- Base score from curve location alignment,
- Add score for trend alignment,
- Add odds enhancers score (next section),
then require `total_score >= min_score`.

---

## 9. Entry Types

There are 3 basic entry types:

### 9.1 Limit Entry (Primary automation-friendly entry)
- **Short:** Place a sell limit at/near supply proximal, stop just above supply distal.
- **Long:** Place a buy limit at/near demand proximal, stop just below demand distal.

### 9.2 Zone Entry (Inside-zone entry)
- Enter anywhere inside the zone.
- Note: Many platforms cannot do this automatically without contingent orders.

**Implementation decision:** Skip zone-entry for v1, as it’s not deterministic. Use limit entry at proximal as default.

### 9.3 Confirmation Entry
- **Short:** If price rallies into supply, reverses, and crosses **below supply proximal**, enter short.
- **Long:** If price drops into demand, reverses, and crosses **above demand proximal**, enter long.

**Implementation decision:** Support as optional mode:
- `entry_mode = "limit"` (default),
- `entry_mode = "confirmation"`.

---

## 10. Exits and Trade Management

Core rules:
1. Always define stop and target (SET).
2. Target must be at least **3R**.
3. Exit before competitive buying/selling begins (before opposing S/D).
4. Manage trade by moving stop only in the direction of profitability.
5. Trail stop methods discussed:
   - Points,
   - Moving averages,
   - Supply/demand-based.

### 10.1 Preset Trade Management Plans
- **Plan #1 (default for v1):**
  - At **2R**, move stop to **breakeven**.
  - At **3R**, take profits (close position).
- **Plan #2:**
  - At **1R**, move stop to breakeven.
  - At **2R**, take profit.

Expose:
- `breakeven_at_r` (default 2.0),
- `take_profit_at_r` (default 3.0).

---

## 11. Odds Enhancers (Setup Scoring)

Odds enhancers objectively measure the quality of a setup based on:

- Level structure (LTF),
- Curve location (HTF),
- Key conditions,
- Asset-class specific,
- All asset classes.

This spec implements the enhancers explicitly described in the doc as a numeric score.

### 11.1 Level Structure. Freshness (Best=3, Good=1.5, Poor=0)
- **Best:** Fresh level (price has not returned).
- **Good:** Minor interaction but not deeply penetrated (implementation approximation).
- **Poor:** Level has been clearly penetrated or repeatedly tested.

**Implementation decision:** Quantify with “touch count”:
- `touches = number of times price enters zone after creation`.
- Score:
  - touches == 0 → 3
  - touches == 1 → 1.5
  - touches >= 2 → 0

### 11.2 Level Structure. Strength of Leg-Out (Best=2, Good=1, Poor=0)
Doc describes strength in terms of a **45–60 degree** or **>=60 degree** move.

**Implementation decision:** Approximate by measuring **slope** and momentum:
- Compute `legout_return = abs(close_end - close_start) / close_start`
- Compute `legout_bars = number of exciting candles in leg-out`
- Strength score:
  - if `legout_return` in top quantile or `legout_return/legout_bars` above threshold → 2
  - mid → 1
  - low → 0

Expose thresholds as parameters.

### 11.3 Level Structure. Time in Base (Best=2, Good=1, Poor=0)
Based on number of base candles:
- **Best:** 3 or fewer candles in base → 2
- **Good:** 4–6 candles → 1
- **Poor:** >6 candles → 0

### 11.4 Curve Location. Profit Zone (Best=3, Good=1.5, Poor=0)
Measures how far the opposing fresh zone is. Larger margin = higher probability.

**Implementation decision:** Use expected R multiple available until opposing zone:
- `max_reward = distance(entry, opposing_zone_proximal)`
- `risk = distance(entry, stop)`
- `available_R = max_reward / risk`
Score:
- available_R >= 3 → 3
- available_R >= 2 → 1.5
- else → 0

### 11.5 Minimum Score
Doc notes you decide the minimum score based on risk aversion.

**Implementation decision:** Use:
- `min_setup_score = 6.0` default
and tune via backtests.

---

## 12. Risk Management and Position Sizing

### 12.1 2% Rule
- Risk **≤ 2%** of account per trade.
- You may risk less. Never exceed 2%.

### 12.2 Position Size Formula
- `risk_amount = account_size * risk_pct`
- `risk_per_unit = abs(entry - stop)`
- `position_size_units = risk_amount / risk_per_unit`

Expose:
- `risk_pct` default 0.02.

---

## 13. Implementation Notes (What v1 will do)

To ship a working algorithmic version:

### v1 Features (Backtest-first)
- Market: **Crypto spot or perp** (Binance-style candles), configurable.
- Entry: **Limit at proximal** (default) with stop beyond distal.
- Setup detection: DBR and RBD zones using boring/exciting candle rules.
- Scoring: Odds enhancers implemented as above with tunable thresholds.
- Filters:
  - Only trade zones aligned with curve and trend scoring.
  - Require minimum available profit zone of 3R.
- Exits:
  - Plan #1 default (BE at 2R, TP at 3R).
- Position sizing:
  - 2% rule.

### v2 Features (After v1 proves itself)
- Confirmation entries,
- Advanced trailing (S&D based trail stop),
- Better “freshness” nuance (partial penetrations),
- Anticipatory trend analysis,
- Asset-class specific enhancers.

---

## 14. Glossary of Strategy Functions (for code)

In code, this strategy naturally maps to:

- `identify_boring_candles()`
- `identify_exciting_candles()`
- `detect_zones_dbr_rbd()`
- `compute_zone_lines_proximal_distal()`
- `is_zone_fresh()`
- `find_nearest_fresh_zones_htf()`
- `curve_location() -> {LOW, EQ, HIGH}`
- `trend_direction_itf() -> {UP, DOWN, SIDEWAYS}`
- `odds_enhancer_score(zone, context) -> float`
- `build_trade_plan(zone, entry_mode) -> entry/stop/target`
- `position_size(account, entry, stop, risk_pct) -> units`
- `manage_trade_plan(plan, current_price) -> stop_updates / exit`

---

## Source

This file is derived from the original documents:
- `trading-app_wiki_TradingStrategyDoc.md at master · gitchrisqueen_trading-app.pdf`
- `TradingStrategyDoc.md`

Images and diagrams were replaced with explicit written definitions and implementable rules.
