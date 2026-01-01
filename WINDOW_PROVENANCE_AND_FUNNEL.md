# Explicit Date-Range Controls, Window Provenance, and Decision Funnel

This document describes the new features added for better control over historical data usage and improved visibility into strategy decision-making.

## Overview

Three major enhancements have been added to the backtest runner:

1. **Explicit Date-Range Controls** - Control which portion of available data to use
2. **Window Provenance Reporting** - Track exactly what data was used vs. available
3. **Decision Funnel Tracking** - See why trades were/weren't taken

## 1. Explicit Date-Range Controls

### Problem

Previously, historical data configs required explicit `start_date` and `end_date`, but there was no easy way to use the full available history. If you downloaded 2 years of data (2023-2024), you had to manually specify the full range or accept using a subset.

### Solution

New config option: `use_full_history`

#### Option A: Explicit Date Range (Original Behavior)

```yaml
data_source: "historical"
start_date: "2024-01-01"
end_date: "2024-03-31"
```

This uses only Q1 2024 data, even if more is available.

#### Option B: Use Full Available History (New)

```yaml
data_source: "historical"
use_full_history: true
```

This automatically:
1. Loads all available data for each required timeframe (15m, 1h, 4h)
2. Finds the common overlapping window across all timeframes
3. Uses the maximum available window

**Example:**
- BTCUSDT 15m: 2023-01-01 to 2024-12-31 (70,176 candles)
- BTCUSDT 1h: 2023-01-01 to 2024-12-31 (17,544 candles)
- BTCUSDT 4h: 2023-01-01 to 2024-12-31 (4,386 candles)
- **Common window used:** 2023-01-01 to 2024-12-31 ✓

### Configuration Examples

#### sd_v1_futures_core.yaml

```yaml
# Time range for backtest
# Option 1: Use explicit dates
# start_date: "2024-01-01"
# end_date: "2024-03-31"

# Option 2: Use full available history
use_full_history: true
```

#### sd_v1_full_history_test.yaml

```yaml
# Use the full available history
use_full_history: true

historical_data:
  exchange: "binance"
  market_type: "futures"
  data_dir: "./data"
```

### Error Handling

The runner will fail loudly if:
- Requested window has too few candles (< 100)
- No common window exists across required timeframes
- Historical data files are missing

## 2. Window Provenance Reporting

### Problem

Previously, it was unclear:
- What portion of available data was actually used
- Whether you were wasting downloaded data
- What the actual time window was after loading

### Solution

Enhanced provenance tracking in artifacts.

### run_manifest.json

New fields added:

```json
{
  "requested_window": {
    "start_date": "2024-01-01",
    "end_date": "2024-03-31",
    "use_full_history": false
  },
  "used_window_global": {
    "start_ts": "2024-01-01T00:00:00+00:00",
    "end_ts": "2024-03-31T23:45:00+00:00"
  },
  "symbol_data_provenance": {
    "BTCUSDT": {
      "available_first_ts": "2023-01-01T00:00:00+00:00",
      "available_last_ts": "2024-12-31T23:45:00+00:00",
      "available_count": 70176,
      "used_first_ts": "2024-01-01T00:00:00+00:00",
      "used_last_ts": "2024-03-31T23:45:00+00:00",
      "used_count": 8640
    }
  }
}
```

### summary.json

Each symbol's data_provenance now includes:

```json
{
  "symbol_results": [
    {
      "symbol": "BTCUSDT",
      "data_provenance": {
        "available_first_ts": "2023-01-01T00:00:00+00:00",
        "available_last_ts": "2024-12-31T23:45:00+00:00",
        "available_count": 70176,
        "used_first_ts": "2024-01-01T00:00:00+00:00",
        "used_last_ts": "2024-03-31T23:45:00+00:00",
        "used_count": 8640
      }
    }
  ]
}
```

### metrics_warnings.json

New warnings for low data utilization:

```json
{
  "warnings": [
    {
      "type": "low_window_utilization",
      "severity": "info",
      "symbol": "BTCUSDT",
      "message": "Symbol BTCUSDT used only 8640/70176 candles (12.3%). Consider use_full_history=true to use more data.",
      "details": {
        "available_count": 70176,
        "used_count": 8640,
        "utilization_pct": 0.123
      }
    }
  ]
}
```

**Warning triggers when:** `used_count < 0.8 * available_count`

This helps identify when you're using less than 80% of downloaded data.

## 3. Decision Funnel Tracking

### Problem

Previously, there was no visibility into:
- How many zones were detected vs. considered for trading
- Why specific setups were rejected
- How many orders expired vs. filled

### Solution

New artifact: `decision_funnel.json`

### Console Output

```
================================================================================
DECISION FUNNEL
================================================================================
Zones Detected:        456
  └─ Fresh:            456
Candidates Evaluated:  4494
  ├─ Rejected (Score): 4167
  └─ Rejected (Min R): 0
Orders Placed:         327
  ├─ Filled:           13
  └─ Expired (TTL):    308
================================================================================
```

### decision_funnel.json

```json
{
  "per_symbol": [
    {
      "symbol": "BTCUSDT",
      "zones_detected": 93,
      "zones_fresh": 93,
      "candidates_evaluated": 371,
      "rejected_curve": 0,
      "rejected_trend": 0,
      "rejected_min_score": 296,
      "rejected_min_rr": 0,
      "orders_placed": 75,
      "orders_filled": 6,
      "orders_expired_ttl": 68
    }
  ],
  "aggregate": {
    "zones_detected": 456,
    "zones_fresh": 456,
    "candidates_evaluated": 4494,
    "rejected_curve": 0,
    "rejected_trend": 0,
    "rejected_min_score": 4167,
    "rejected_min_rr": 0,
    "orders_placed": 327,
    "orders_filled": 13,
    "orders_expired_ttl": 308
  }
}
```

### Funnel Metrics Explained

- **zones_detected**: Total zones found (DBR/RBD patterns)
- **zones_fresh**: Zones that haven't been revisited (fresh zones)
- **candidates_evaluated**: Number of times zones were considered for trading
- **rejected_curve**: Rejected due to HTF curve analysis (demand at HIGH curve, supply at LOW curve)
- **rejected_trend**: Rejected due to ITF trend analysis (trend not aligned)
- **rejected_min_score**: Rejected due to setup score < min_setup_score (default 6.0)
- **rejected_min_rr**: Rejected due to R-multiple < min_reward_risk (default 3.0)
- **orders_placed**: Limit orders placed (passed all gates)
- **orders_filled**: Orders that were filled
- **orders_expired_ttl**: Orders that expired (TTL timeout, default 10 bars)

### Use Cases

**Debugging low fill rate:**
```
Orders Placed: 327
Orders Filled: 13
Orders Expired (TTL): 308
```
→ Only 4% fill rate. Consider:
- Increasing TTL (time-to-live for limit orders)
- Adjusting entry logic (limit vs. confirmation entry)
- Reviewing zone quality/freshness

**Debugging low trade count:**
```
Candidates Evaluated: 4494
Rejected (Score): 4167
Orders Placed: 327
```
→ 93% rejection due to low setup score. Consider:
- Lowering min_setup_score threshold
- Reviewing odds enhancer scoring weights

## Usage Examples

### Example 1: Use Full History

```bash
# Edit config
vim experiments/sd_v1_futures_core.yaml

# Set use_full_history: true
# Comment out start_date/end_date

# Run backtest
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml

# Check provenance
cat artifacts/sd_v1/*/run_manifest.json | jq '.requested_window'
cat artifacts/sd_v1/*/run_manifest.json | jq '.used_window_global'
```

### Example 2: Check Window Utilization

```bash
# Run backtest with narrow window
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml

# Check warnings
cat artifacts/sd_v1/*/metrics_warnings.json | jq '.warnings[] | select(.type == "low_window_utilization")'
```

### Example 3: Analyze Decision Funnel

```bash
# Run backtest
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml

# Check aggregate funnel
cat artifacts/sd_v1/*/decision_funnel.json | jq '.aggregate'

# Check per-symbol funnel
cat artifacts/sd_v1/*/decision_funnel.json | jq '.per_symbol[] | select(.symbol == "BTCUSDT")'
```

## Testing

Comprehensive tests added in `tests/test_window_provenance.py`:

- `test_full_history_uses_all_available_data` - Validates use_full_history=true
- `test_run_manifest_has_window_fields` - Validates run_manifest structure
- `test_date_range_slicing_works` - Validates start_date/end_date slicing
- `test_decision_funnel_json_created` - Validates decision_funnel.json creation
- `test_funnel_counts_are_logical` - Validates funnel metric consistency
- `test_low_utilization_generates_warning` - Validates warning triggers

Run tests:
```bash
poetry run pytest tests/test_window_provenance.py -v
```

## Backward Compatibility

All existing configs work without modification:

- Configs without `use_full_history` default to `False`
- Configs with explicit `start_date/end_date` continue to work
- Synthetic data configs unaffected
- All existing artifact files still generated

## Related Files

**Core Implementation:**
- `strategies/supply_demand_v1/data_loader.py` - Enhanced candle loading with metadata
- `strategies/supply_demand_v1/runner.py` - Window tracking and funnel metrics

**Configuration:**
- `experiments/sd_v1_futures_core.yaml` - Example with use_full_history
- `experiments/sd_v1_full_history_test.yaml` - Test config

**Tests:**
- `tests/test_window_provenance.py` - Comprehensive test suite

**Documentation:**
- `docs/DATA_PIPELINE.md` - Data download and management
- `docs/HISTORICAL_DATA_GUIDE.md` - Using historical data
