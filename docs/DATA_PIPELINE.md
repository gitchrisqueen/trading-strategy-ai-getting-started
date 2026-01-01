# Binance USDT-M Futures Data Pipeline Guide

This guide explains how to bootstrap and maintain historical OHLCV data for Binance USDT-margined perpetual futures contracts.

## Overview

The data pipeline provides:
- **Automated downloads** from Binance's free bulk data service
- **Incremental updates** via CCXT to keep data current
- **Caching** to avoid redundant downloads
- **Validation** to ensure data integrity
- **Persistence** in GitHub Codespaces

## Quick Start

### 1. Bootstrap Historical Data

Download bulk historical data from Binance Vision:

```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT ETHUSDT \
  --timeframes 15m 1h 4h \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --out ./data/binance_futures
```

**What happens:**
- Downloads daily zip files from https://data.binance.vision/
- Automatically handles CSV files with or without header rows
- Extracts and consolidates candles
- Removes duplicates and sorts by timestamp
- Writes CSV files: `./data/binance_futures/{SYMBOL}_{TIMEFRAME}.csv`
- Caches zip files in `./data/.cache/binance_vision/`
- Updates manifest: `./data/binance_futures/_manifest.json`

**Output format:**
```csv
datetime,open,high,low,close,volume
2023-01-01 00:00:00,16547.50,16600.00,16500.00,16580.25,1234.56
2023-01-01 00:15:00,16580.25,16620.00,16570.00,16610.50,2345.67
```

### 2. Update with Latest Data

Fetch new candles using CCXT:

```bash
python data_tools/binance_usdm_ohlcv.py update \
  --symbols BTCUSDT ETHUSDT \
  --timeframes 15m 1h 4h \
  --out ./data/binance_futures
```

**What happens:**
- Reads last timestamp from each CSV
- Fetches new candles via CCXT (binanceusdm)
- Appends new candles (skips duplicates)
- Updates manifest

### 3. Validate Data Quality

Check for gaps, duplicates, and invalid data. **Timeframes are automatically detected from filenames!**

```bash
# Auto-detect timeframes (recommended)
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --verbose
```

**Advanced options:**
```bash
# Only validate 1h files
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --timeframe 1h

# Allow up to 2 missing intervals (for known exchange downtime)
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --max-gap-intervals 2
```

**What's checked:**
- ✓ Monotonic timestamps (strictly increasing)
- ✓ No duplicate timestamps
- ✓ Expected interval spacing (15m files use 15m interval, 1h files use 1h interval, etc.)
- ✓ Gap detection (missing candles)
- ✓ Valid OHLC relationships (high >= low, etc.)
- ✓ Positive prices and volumes

**Timeframe Detection:**
The validator automatically detects the timeframe from the filename pattern:
- `BTCUSDT_15m.csv` → validates with 15-minute intervals
- `ETHUSDT_1h.csv` → validates with 1-hour intervals
- `BNBUSDT_4h.csv` → validates with 4-hour intervals

This eliminates false "gap detected" errors that occurred when all files were validated with a single timeframe.

### 4. Run Backtest

Use the downloaded data in experiments:

```bash
python scripts/run_supply_demand_v1.py \
  --config experiments/sd_v1_futures_core.yaml
```

The runner will load CSVs from `./data/binance_futures/` based on the config.

## Data Persistence in Codespaces

### How Persistence Works

- **Location**: `./data/` lives in the repository workspace (`/workspaces/trading-strategy-ai-getting-started/data/`)
- **Persists across**:
  - ✓ Codespace stop/start
  - ✓ Codespace rebuild (as long as workspace is preserved)
- **Does NOT persist across**:
  - ✗ Codespace deletion
  - ✗ Repository clone to new Codespace

### Best Practices

1. **Keep ./data in .gitignore**
   - Data files are large (100+ MB per symbol/timeframe)
   - Regenerate from bootstrap script instead of committing

2. **Run bootstrap once per Codespace**
   - Bootstrap is idempotent: won't redownload existing files
   - Re-run if Codespace is deleted and recreated

3. **Run update regularly**
   - Update fetches only new candles (fast)
   - Schedule updates before backtest runs

### Backup and Export (Optional)

To backup your data or share it between Codespaces:

#### Export Data Bundle

```bash
# Create tarball
tar -czf data_backup.tar.gz \
  ./data/binance_futures/*.csv \
  ./data/binance_futures/_manifest.json

# Download via Codespace UI or copy to external storage
```

#### Import Data Bundle

```bash
# Upload tarball to Codespace
# Extract
tar -xzf data_backup.tar.gz

# Validate
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --timeframe 15m
```

#### Use Git LFS (Not Recommended)

While Git LFS could store data files, we **do not recommend it** because:
- Adds complexity to setup
- Costs money for bandwidth
- Bootstrap is fast enough to regenerate data

## Using Make/Scripts

Convenience wrappers for common operations:

### Via Make (if Makefile has targets)

```bash
# Bootstrap core symbols
make data-bootstrap

# Update data
make data-update

# Validate data
make data-validate
```

### Via Scripts

```bash
# Bootstrap
./scripts/data_bootstrap.sh

# Update
./scripts/data_update.sh

# Validate
./scripts/data_validate.sh
```

## Caching Strategy

### Bootstrap Cache

- **Location**: `./data/.cache/binance_vision/`
- **Contents**: Daily zip files from Binance Vision
- **Behavior**:
  - First bootstrap: downloads and caches zips
  - Second bootstrap: reads from cache (fast)
  - Use `--force` to bypass cache and redownload

### Manifest Tracking

The manifest file (`./data/binance_futures/_manifest.json`) tracks:

```json
{
  "BTCUSDT_15m": {
    "last_updated": "2024-01-01T12:00:00+00:00",
    "first_ts": "2023-01-01 00:00:00",
    "last_ts": "2024-12-31 23:45:00",
    "candle_count": 35040,
    "checksum": "abc123def456..."
  }
}
```

**Uses:**
- Tracks last update time
- Verifies data integrity (checksum)
- Avoids redundant downloads

## Advanced Usage

### Custom Date Ranges

Bootstrap specific date ranges:

```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT \
  --timeframes 15m \
  --start 2024-01-01 \
  --end 2024-01-31 \
  --out ./data/binance_futures
```

### Multiple Timeframes

Bootstrap multiple timeframes efficiently:

```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT ETHUSDT BNBUSDT \
  --timeframes 15m 1h 4h 1d \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --out ./data/binance_futures
```

### Force Redownload

Force redownload even if files exist:

```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT \
  --timeframes 15m \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --out ./data/binance_futures \
  --force
```

### Custom Cache Directory

Use a different cache location:

```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT \
  --timeframes 15m \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --out ./data/binance_futures \
  --cache /tmp/binance_cache
```

## Troubleshooting

### "No data found for symbol"

**Cause**: Binance Vision doesn't have data for that date range.

**Solutions**:
- Check if symbol exists: https://data.binance.vision/?prefix=data/futures/um/daily/klines/
- Adjust start/end dates to available range
- Use CCXT update to fetch recent data (if bootstrap fails)

### "ccxt not installed"

**Cause**: Update command requires CCXT library.

**Solution**:
```bash
pip install ccxt
```

### "Gap detected" validation errors

**Cause**: Missing candles in data (exchange downtime, data availability).

**Solutions**:
- Acceptable: Use `--max-gap-multiplier` to tolerate small gaps
- Fix: Re-bootstrap with different date range
- Workaround: Fill gaps manually or skip validation

### "Duplicate timestamp" validation errors

**Cause**: Same timestamp appears multiple times.

**Solutions**:
- Re-bootstrap with `--force` (removes duplicates automatically)
- Manual fix: Edit CSV to remove duplicate lines

### "Non-monotonic timestamps"

**Cause**: Timestamps not sorted or decreasing.

**Solutions**:
- Re-bootstrap (automatically sorts)
- Manual fix: Sort CSV by datetime column

## Data Sources

### Binance Vision (Bootstrap)

- **URL**: https://data.binance.vision/
- **Format**: Daily zip files with CSV data
- **Cost**: Free
- **Limitations**:
  - Historical data only (not real-time)
  - Daily granularity (one zip per day)
  - May have gaps or missing days

### CCXT (Update)

- **Exchange**: binanceusdm
- **Format**: OHLCV arrays
- **Cost**: Free (rate limited)
- **Limitations**:
  - Rate limits (handled by library)
  - Limited history (typically 1000 candles max per request)
  - Use for recent data only

## Workflow Recommendations

### Initial Setup (Once)

1. Bootstrap historical data for core symbols:
   ```bash
   make data-bootstrap
   # or
   python data_tools/binance_usdm_ohlcv.py bootstrap \
     --symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT \
     --timeframes 15m 1h 4h \
     --start 2023-01-01 \
     --end 2024-12-31 \
     --out ./data/binance_futures
   ```

2. Validate data:
   ```bash
   make data-validate
   ```

3. Run test backtest:
   ```bash
   python scripts/run_supply_demand_v1.py \
     --config experiments/sd_v1_futures_core.yaml
   ```

### Daily Workflow

1. Update data with latest candles:
   ```bash
   make data-update
   ```

2. Validate (optional, if you suspect issues):
   ```bash
   make data-validate
   ```

3. Run backtests:
   ```bash
   python scripts/run_supply_demand_v1.py \
     --config experiments/sd_v1_futures_expanded.yaml
   ```

### Before Important Runs

1. Validate data integrity:
   ```bash
   python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --timeframe 15m --verbose
   ```

2. Check manifest:
   ```bash
   cat ./data/binance_futures/_manifest.json
   ```

3. Update if last_updated is old:
   ```bash
   make data-update
   ```

## File Organization

```
data/
├── README.md
├── .cache/
│   └── binance_vision/
│       ├── BTCUSDT-15m-2023-01-01.zip
│       ├── BTCUSDT-15m-2023-01-02.zip
│       └── ...
└── binance_futures/
    ├── _manifest.json
    ├── BTCUSDT_15m.csv
    ├── BTCUSDT_1h.csv
    ├── BTCUSDT_4h.csv
    ├── ETHUSDT_15m.csv
    ├── ETHUSDT_1h.csv
    └── ...
```

## Performance Notes

- **Bootstrap**: ~1-2 minutes per symbol/timeframe/year
- **Update**: ~5-10 seconds per symbol/timeframe
- **Validation**: ~1-2 seconds per file
- **CSV loading**: Fast (<1 second per file in backtest)

## See Also

- [Historical Data Guide](./HISTORICAL_DATA_GUIDE.md) - Existing historical data integration
- [Experiment Runner Instructions](.github/instructions/experiments_runner.instructions.md) - How experiments work
- [Supply & Demand Strategy](strategies/supply_demand_v1/README.md) - Strategy documentation
