# Data Provenance + Metrics Consistency Audit - Implementation Summary

## Problems Addressed

### Problem 1: max_drawdown Always 0.0 ✓ FIXED
**Before:** All symbol results showed `max_drawdown: 0.0` regardless of trading activity.

**After:** Each symbol now correctly calculates drawdown from equity curve tracking:
- BTC/USDT: $664.92 drawdown (7 trades)
- ETH/USDT: $1,240.75 drawdown (11 trades)
- ATOM/USDT: $1,286.36 drawdown (7 trades)

**Implementation:**
- Added `equity_curve` tracking in `execute_backtest_for_symbol()`
- Implemented `calculate_max_drawdown()` function
- Updated `SymbolResult` dataclass to include equity curve
- Added comprehensive tests for drawdown calculation

### Problem 2: Inconsistent Metrics ✓ FIXED
**Before:** No validation for impossible metric combinations (e.g., large P&L with near-zero R).

**After:** Automated consistency checks with warnings:
- Detects `max_drawdown == 0.0` while `trades_filled > 0`
- Detects `abs(avg_r_realized) < 0.02` while `abs(total_pnl) > $500`
- Outputs warnings to `metrics_warnings.json`

**Implementation:**
- Created `check_metrics_consistency()` function
- Added `metrics_warnings` to `ExperimentResult`
- Writes `metrics_warnings.json` artifact with structured warnings

### Problem 3: Unclear Portfolio Accounting ✓ FIXED
**Before:** `overall_pnl` implied combined portfolio but each symbol was independent.

**After:** Explicit accounting mode clarification:
- `accounting_mode: "per_symbol_independent"` in summary.json
- `sum_of_symbol_pnls` replaces misleading "overall_pnl"
- Documentation clarifies independent backtesting

**Implementation:**
- Added `accounting_mode` field to aggregate_metrics
- Renamed aggregate P&L to `sum_of_symbol_pnls`
- Kept `overall_pnl` for backward compatibility

## Deliverables Completed

### A) Data Provenance (run_manifest.json) ✓ COMPLETE
Enhanced `run_manifest.json` with comprehensive data provenance:

```json
{
  "datasource_name": "synthetic",
  "is_synthetic_data": true,
  "candle_timeframe": "15m",
  "data_generation": {
    "generator_module": "strategies.supply_demand_v1.runner.generate_synthetic_candles",
    "base_seed": 42,
    "num_candles": 2000,
    "volatility": 0.02
  },
  "symbol_data_provenance": {
    "BTC/USDT": {
      "first_timestamp": "2024-01-01T00:00:00+00:00",
      "last_timestamp": "2024-01-21T19:45:00+00:00",
      "first_close": 101.44,
      "last_close": 19.92,
      "candle_count": 2000,
      "checksum": "584c93d117b281e8e3a993e24bea72d1"
    }
  }
}
```

### B) Metrics Consistency Checks (metrics_warnings.json) ✓ COMPLETE
New artifact validates metrics consistency:

```json
{
  "total_warnings": 0,
  "warnings": []
}
```

Warnings are triggered for:
1. Zero drawdown with filled trades
2. Low average R with large P&L

### C) Drawdown Correctness ✓ COMPLETE
- Equity curve tracked per symbol
- Max drawdown computed correctly
- Tests validate calculation accuracy

### D) Portfolio Mode Clarification ✓ COMPLETE
- `accounting_mode` field added to summary.json
- Clear labeling of independent vs. combined accounting
- Documentation updated

### E) Tests ✓ COMPLETE
Added comprehensive test coverage:
- `test_runner_provenance.py` (14 tests):
  - Drawdown calculation (6 tests)
  - Metrics consistency warnings (4 tests)
  - Data provenance validation (4 tests)
- Updated existing tests for new function signatures
- All 29 tests passing

## Artifact Schema Changes

### run_manifest.json
**New fields:**
- `datasource_name` (string): Data source identifier
- `is_synthetic_data` (boolean): Synthetic vs. real data flag
- `candle_timeframe` (string): Primary timeframe (e.g., "15m")
- `data_generation` (object): Generator metadata
  - `generator_module` (string): Python module path
  - `base_seed` (int): Random seed for reproducibility
  - `num_candles` (int): Candles per symbol
  - `volatility` (float): Price volatility parameter
- `symbol_data_provenance` (object): Per-symbol data details
  - `first_timestamp` (string): ISO timestamp of first candle
  - `last_timestamp` (string): ISO timestamp of last candle
  - `first_close` (float): First close price
  - `last_close` (float): Last close price
  - `candle_count` (int): Total candles for symbol
  - `checksum` (string): MD5 hash of close prices

### summary.json
**New fields:**
- `aggregate_metrics.accounting_mode` (string): "per_symbol_independent" or "portfolio_combined"
- `aggregate_metrics.sum_of_symbol_pnls` (float): Sum of independent P&Ls
- `symbol_results[].max_drawdown` (float): Correctly calculated drawdown
- `symbol_results[].data_provenance` (object): Per-symbol data metadata

**Modified:**
- `symbol_results[].equity_curve` (list): Now tracked but excluded from JSON (too large)

### metrics_warnings.json (NEW)
```json
{
  "total_warnings": 0,
  "warnings": [
    {
      "type": "zero_drawdown_with_trades",
      "severity": "warning",
      "symbol": "BTC/USDT",
      "message": "Symbol BTC/USDT has 10 filled trades but max_drawdown is 0.0...",
      "details": {
        "trades_filled": 10,
        "max_drawdown": 0.0,
        "total_pnl": 500.0
      }
    }
  ]
}
```

## Verification

### Test Results
```
tests/test_runner.py: 15 passed
tests/test_runner_provenance.py: 14 passed
Total: 29 passed
```

### Example Experiment Run
```
Config: experiments/sd_v1_wide_symbols.yaml
Symbols: 15 (BTC, ETH, SOL, MATIC, AVAX, DOT, LINK, UNI, ATOM, ADA, XRP, LTC, BCH, DOGE, SHIB)
Total Trades: 135
Win Rate: 31.11%
Sum of Symbol P&Ls: $4,359.05

Max Drawdowns (sample):
- BTC/USDT: $664.92 (was 0.0)
- ETH/USDT: $1,240.75 (was 0.0)
- ATOM/USDT: $1,286.36 (was 0.0)
```

## Backward Compatibility

All changes maintain backward compatibility:
- Existing `overall_pnl` field kept alongside new `sum_of_symbol_pnls`
- New fields added without removing existing ones
- Existing tests updated but behavior unchanged
- Artifact file names unchanged

## Constraints Maintained

✓ No changes to trading logic (zone detection, scoring, entry rules)
✓ No changes to strategy behavior
✓ All changes are reporting correctness and provenance only

## Usage Example

```bash
# Run experiment
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Check artifacts
ls artifacts/sd_v1/<timestamp>_<hash>/
# - summary.json (with accounting_mode and correct drawdowns)
# - run_manifest.json (with full data provenance)
# - metrics_warnings.json (consistency checks)
# - trades.csv
# - zones.csv
# - violations.json

# Inspect data provenance
cat artifacts/sd_v1/<timestamp>_<hash>/run_manifest.json | jq '.symbol_data_provenance'

# Check for warnings
cat artifacts/sd_v1/<timestamp>_<hash>/metrics_warnings.json | jq '.warnings'
```

## Future Enhancements

The following were identified but marked as future work:
1. **Portfolio-combined accounting mode**: Aggregate equity curve across symbols with shared capital pool
2. **Real-time data provenance**: Support for live exchange data with API metadata
3. **Advanced warning rules**: More sophisticated metric validation (Sharpe ratio checks, etc.)
4. **Equity curve visualization**: Export equity curves for charting tools

## Acceptance Criteria Status

✓ Experiments rerun produce run_manifest.json with provenance
✓ max_drawdown is computed and not always 0.0
✓ metrics_warnings.json appears when appropriate
✓ tests pass (29/29)
✓ Accounting mode clarified in summary.json
✓ No changes to trading logic
