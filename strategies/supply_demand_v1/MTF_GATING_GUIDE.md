# Multi-Timeframe Gating Implementation Guide

## Overview

This document describes the multi-timeframe (MTF) gating implementation for the Supply & Demand V1 strategy. The gating system uses Higher Timeframe (HTF) curve analysis and Intermediate Timeframe (ITF) trend analysis to filter trades, improving setup quality.

## Architecture

### 1. Curve Analysis (HTF)

**Purpose:** Determine if price is HIGH, LOW, or in EQUILIBRIUM within the broader range.

**Functions:**
- `find_nearest_fresh_supply_above(price, zones_htf)` - Find nearest fresh supply zone above price
- `find_nearest_fresh_demand_below(price, zones_htf)` - Find nearest fresh demand zone below price
- `classify_curve(price, supply_proximal, demand_proximal)` - Returns "LOW" | "EQ" | "HIGH"

**Algorithm:**
1. Identify nearest fresh supply above and nearest fresh demand below current price
2. Use their proximal lines to define range
3. Split range into thirds:
   - Bottom third = "LOW"
   - Middle third = "EQ"
   - Top third = "HIGH"

### 2. Trend Analysis (ITF)

**Purpose:** Determine if trend is UP, DOWN, or SIDEWAYS.

**Functions:**
- `detect_pivot_highs_lows(candles, lookback)` - Detect pivot points
- `classify_trend(pivot_highs, pivot_lows, candles, pivots_to_consider)` - Returns "UP" | "DOWN" | "SIDEWAYS"

**Algorithm:**
1. Detect pivot highs and lows using lookback window
2. Analyze most recent N pivots
3. Classify based on pattern:
   - Higher Highs + Higher Lows → "UP"
   - Lower Highs + Lower Lows → "DOWN"
   - Mixed or equal → "SIDEWAYS"

### 3. Trade Gating Logic

**Purpose:** Filter trades based on curve + trend alignment.

**Function:**
- `should_allow_trade(zone, curve_state, trend_state, base_score, parameters)` - Returns (allowed: bool, final_score: float)

**Gating Rules:**

#### Rule 1: LOW Curve
- **Allow:** Demand LONG trades (buy at support)
- **Block:** Supply SHORT trades
- **Rationale:** Price is near support, expect upward movement

#### Rule 2: HIGH Curve
- **Allow:** Supply SHORT trades (sell at resistance)
- **Block:** Demand LONG trades
- **Rationale:** Price is near resistance, expect downward movement

#### Rule 3: EQUILIBRIUM (EQ) Curve
- **Requires:** Trend alignment + higher score threshold
- **LONG trades:** Require "UP" trend
- **SHORT trades:** Require "DOWN" trend
- **Score bonus:** Add `eq_min_setup_score_bonus` (default +1.0) to base score
- **Rationale:** In the middle of range, need trend confirmation

## Configuration Parameters

### Multi-Timeframe Settings
```python
htf_tf: str = "4h"  # Higher timeframe for curve analysis
itf_tf: str = "1h"  # Intermediate timeframe for trend
ltf_tf: str = "15m" # Lower timeframe for zones and entry
pivot_len: int = 5  # Lookback for pivot detection
pivots_to_consider: int = 4  # Number of recent pivots to analyze
```

### Gating Controls
```python
allow_eq_trades: bool = True  # Allow trades in EQUILIBRIUM
eq_requires_trend_alignment: bool = True  # Require trend alignment for EQ
eq_min_setup_score_bonus: float = 1.0  # Score bonus for EQ trades
```

## Usage Example

```python
from strategies.supply_demand_v1.strategy import (
    find_nearest_fresh_zones_htf,
    classify_curve,
    classify_trend,
    should_allow_trade,
    detect_pivot_highs_lows,
    SupplyDemandParameters,
)

# Initialize parameters
params = SupplyDemandParameters()

# Analyze curve (HTF)
supply_above, demand_below = find_nearest_fresh_zones_htf(htf_candles, current_price, params)
supply_proximal = supply_above.proximal if supply_above else None
demand_proximal = demand_below.proximal if demand_below else None
curve_state = classify_curve(current_price, supply_proximal, demand_proximal)

# Analyze trend (ITF)
pivot_highs, pivot_lows = detect_pivot_highs_lows(itf_candles, params.pivot_len)
trend_state = classify_trend(pivot_highs, pivot_lows, itf_candles, params.pivots_to_consider)

# Apply gating to each zone
for zone in zones:
    base_score = calculate_zone_score(zone)  # Your scoring logic
    
    allowed, final_score = should_allow_trade(
        zone, 
        curve_state, 
        trend_state, 
        base_score, 
        params
    )
    
    if allowed:
        # Proceed with trade plan
        trade_plan = build_trade_plan(zone, final_score, ...)
```

## Gating Statistics Tracking

Track gating effectiveness:

```python
gating_stats = {
    'total_zones': 0,
    'passed_scoring': 0,
    'blocked_by_curve': 0,
    'blocked_by_trend': 0,
    'allowed_trades': 0,
    'curve_states': {'LOW': 0, 'EQ': 0, 'HIGH': 0},
    'trend_states': {'UP': 0, 'DOWN': 0, 'SIDEWAYS': 0}
}
```

## Testing

Comprehensive test coverage in `tests/test_supply_demand_mtf_gating.py`:

- **Curve Classification Tests** (5 tests)
  - LOW, EQ, HIGH positions
  - Boundary cases
  - Missing zones

- **Trend Classification Tests** (4 tests)
  - Uptrend (HH/HL)
  - Downtrend (LH/LL)
  - Sideways (mixed)
  - Insufficient data

- **Zone Finding Tests** (3 tests)
  - Find supply above
  - Find demand below
  - No fresh zones

- **Trade Gating Tests** (12 tests)
  - LOW curve rules
  - HIGH curve rules
  - EQ curve rules
  - Trend alignment
  - Configuration options

All tests passing: **24/24** ✓

## Performance Considerations

1. **Curve Analysis:** O(n) where n = number of HTF zones
2. **Trend Analysis:** O(m) where m = number of ITF candles
3. **Gating Check:** O(1) constant time

Overall performance impact is minimal, suitable for real-time trading.

## Future Enhancements

Potential improvements for future PRs:

1. **Dynamic timeframe selection** based on market volatility
2. **Weighted trend scoring** instead of binary UP/DOWN/SIDEWAYS
3. **Volume-based curve refinement**
4. **Machine learning for optimal gating thresholds**
5. **Multiple HTF levels** (e.g., Daily + 4H curves)

## References

- Strategy Specification: `TradingStrategySpec.md` (sections 5-8)
- Core Implementation: `strategy.py` (lines 816-1074)
- Test Suite: `test_supply_demand_mtf_gating.py`
- Demo Notebook: `notebooks/supply_demand_v1_backtest.ipynb`
