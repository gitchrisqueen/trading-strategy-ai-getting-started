# Implementation Summary: Window Provenance & Decision Funnel

## Completed: January 1, 2026

### Problem Statement
The backtest runner had 2 years of downloaded historical data (2023-2024) but configs used only small subsets (e.g., Q1 2024). There was:
- No way to easily use full available history
- No visibility into which data was actually used vs. available
- No tracking of why trades were/weren't taken (decision funnel)

### Solution Implemented

#### 1. Explicit Date-Range Controls
Added `use_full_history` config option to automatically use the maximum available data window:

```yaml
# OLD: Manual date specification
start_date: "2024-01-01"
end_date: "2024-03-31"

# NEW: Auto-detect full history
use_full_history: true
```

**Behavior:**
- Loads all available data for each timeframe (15m, 1h, 4h)
- Finds common overlapping window across timeframes
- Uses maximum available window
- Fails loudly if data insufficient

#### 2. Window Provenance Reporting
Enhanced artifacts with detailed window tracking:

**run_manifest.json:**
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
  }
}
```

**Per-symbol provenance in summary.json:**
```json
{
  "data_provenance": {
    "available_first_ts": "2023-01-01T00:00:00+00:00",
    "available_last_ts": "2024-12-31T23:45:00+00:00",
    "available_count": 70176,
    "used_first_ts": "2024-01-01T00:00:00+00:00",
    "used_last_ts": "2024-03-31T23:45:00+00:00",
    "used_count": 8640
  }
}
```

**Low utilization warnings in metrics_warnings.json:**
```json
{
  "type": "low_window_utilization",
  "message": "Symbol used only 8640/70176 candles (12.3%). Consider use_full_history=true.",
  "details": {
    "utilization_pct": 0.123
  }
}
```

#### 3. Decision Funnel Tracking
New artifact `decision_funnel.json` tracking why trades were/weren't taken:

**Console output:**
```
DECISION FUNNEL
Zones Detected:        456
  └─ Fresh:            456
Candidates Evaluated:  4494
  ├─ Rejected (Score): 4167
Orders Placed:         327
  ├─ Filled:           13
  └─ Expired (TTL):    308
```

**Metrics tracked:**
- zones_detected, zones_fresh
- candidates_evaluated
- rejected_curve, rejected_trend, rejected_min_score, rejected_min_rr
- orders_placed, orders_filled, orders_expired_ttl

### Files Modified

**Core Implementation:**
- `strategies/supply_demand_v1/data_loader.py` (+110 lines)
  - Added `return_metadata` parameter to load_historical_candles
  - Added `find_common_window()` to detect overlapping timeframes
  - Enhanced metadata tracking (available vs. used counts)

- `strategies/supply_demand_v1/runner.py` (+326 lines, -64 lines)
  - Added `DecisionFunnel` dataclass
  - Enhanced `load_candles_from_config()` with use_full_history support
  - Updated `execute_backtest_for_symbol()` to track funnel metrics
  - Modified `run_backtest_experiment()` to collect window metadata
  - Enhanced `write_artifacts()` to output decision_funnel.json

**Configuration:**
- `experiments/sd_v1_futures_core.yaml` - Added use_full_history option
- `experiments/sd_v1_futures_expanded.yaml` - Added use_full_history comments
- `experiments/sd_v1_futures_stress.yaml` - Added data_source config
- `experiments/sd_v1_full_history_test.yaml` - New test config
- `experiments/sd_v1_narrow_window_test.yaml` - New test config

**Tests:**
- `tests/test_window_provenance.py` (+550 lines)
  - Test full history usage
  - Test date range slicing
  - Test run_manifest structure
  - Test decision funnel creation
  - Test low utilization warnings
  - Test backward compatibility

**Documentation:**
- `WINDOW_PROVENANCE_AND_FUNNEL.md` - Comprehensive usage guide

### Testing Results

**Verified with sd_v1_default.yaml (synthetic data):**
- ✓ Decision funnel printed to console
- ✓ decision_funnel.json created with valid structure
- ✓ run_manifest.json includes requested_window and used_window_global
- ✓ summary.json includes enhanced data_provenance
- ✓ metrics_warnings.json created
- ✓ All 13 trades validated (no violations)

**Test Suite:**
- ✓ 13 test cases in test_window_provenance.py
- ✓ Tests cover all new functionality
- ✓ Tests use temporary synthetic fixtures (no external dependencies)

### Backward Compatibility

All existing configs work without modification:
- ✓ Configs without use_full_history default to False
- ✓ Configs with start_date/end_date continue to work
- ✓ Synthetic data configs unaffected
- ✓ All existing artifacts still generated

### No Trading Logic Changes

As required:
- ✓ Zone detection unchanged
- ✓ Scoring logic unchanged
- ✓ Entry/exit logic unchanged
- ✓ Trade management unchanged
- ✓ Only controls + reporting added

### Usage Examples

**Enable full history:**
```bash
# Edit config to set use_full_history: true
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml
```

**Check window utilization:**
```bash
cat artifacts/sd_v1/*/metrics_warnings.json | jq '.warnings[] | select(.type == "low_window_utilization")'
```

**Analyze decision funnel:**
```bash
cat artifacts/sd_v1/*/decision_funnel.json | jq '.aggregate'
```

### Benefits

1. **Maximize data usage** - Easily use all downloaded data
2. **Transparency** - Know exactly what data was used
3. **Debugging** - Understand why trades weren't taken
4. **Efficiency** - Warnings identify wasted data downloads
5. **Reproducibility** - Window provenance ensures reproducible results

### Related Documentation

- [WINDOW_PROVENANCE_AND_FUNNEL.md](WINDOW_PROVENANCE_AND_FUNNEL.md) - Complete usage guide
- [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md) - Data download pipeline
- [docs/HISTORICAL_DATA_GUIDE.md](docs/HISTORICAL_DATA_GUIDE.md) - Historical data usage

### Commit History

1. `1246fda` - Initial implementation of date-range controls, window provenance, and funnel tracking
2. `f840d65` - Added comprehensive tests and fixed Tuple import
3. `09b692b` - Updated configs and added documentation

### Status: COMPLETE ✓

All deliverables from the problem statement have been implemented, tested, and documented.
