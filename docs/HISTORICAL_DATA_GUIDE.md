# Real Historical Futures Data Integration - User Guide

This guide explains how to use the new historical futures data integration in the Supply & Demand V1 strategy runner.

## Overview

The runner now supports two data sources:
1. **Synthetic** - Generated fake data for testing (default, backward compatible)
2. **Historical** - Real historical candle data from CSV files

## Quick Start

### Using Historical Data

1. **Prepare your data** - Place CSV files in the correct location:
   ```
   ./data/binance_futures/BTCUSDT_15m.csv
   ./data/binance_futures/ETHUSDT_15m.csv
   ```

2. **Update your config** - Add these lines to your YAML config:
   ```yaml
   # Data source: "synthetic" or "historical"
   data_source: "historical"
   
   # Historical data configuration
   historical_data:
     exchange: "binance"
     market_type: "futures"
     data_dir: "./data"
   ```

3. **Run the experiment**:
   ```bash
   python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml
   ```

### Using Synthetic Data (Default)

No changes needed! Existing configs continue to work:

```yaml
# Data source defaults to "synthetic" if not specified
data_generation:
  num_candles: 1000
  volatility: 0.02
  seed: 42
```

## CSV Format Requirements

Historical data CSV files must follow this format:

```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234567.89
2024-01-01 00:15:00,42300.0,42800.0,42100.0,42600.0,2345678.90
```

### Validation Rules

The loader validates all data with strict checks:

- ✅ **Minimum candles**: At least 100 candles required
- ✅ **Monotonic timestamps**: Timestamps must strictly increase
- ✅ **Positive values**: All OHLC values must be > 0
- ✅ **Complete data**: All columns (timestamp, open, high, low, close, volume) required
- ✅ **Date range coverage**: Sufficient data for experiment start/end dates

### Error Handling

The runner **fails loudly** if historical data is invalid:

```
HistoricalDataError: Historical data file not found: ./data/binance_futures/BTCUSDT_15m.csv
Expected location: ./data/binance_futures/BTCUSDT_15m.csv
Please ensure historical data is downloaded and placed in the correct location.
```

**No silent fallback to synthetic data!** This ensures data integrity.

## Provenance Tracking

### run_manifest.json

The manifest now explicitly tracks data source:

#### Synthetic Data:
```json
{
  "data_source": "synthetic",
  "datasource_name": "synthetic",
  "is_synthetic_data": true,
  "exchange": null,
  "market_type": null,
  "data_generation": {
    "generator_module": "strategies.supply_demand_v1.runner.generate_synthetic_candles",
    "base_seed": 42,
    "num_candles": 1000,
    "volatility": 0.02
  }
}
```

#### Historical Data:
```json
{
  "data_source": "historical",
  "datasource_name": "binance_futures",
  "is_synthetic_data": false,
  "exchange": "binance",
  "market_type": "futures",
  "symbol_data_provenance": {
    "BTCUSDT": {
      "first_timestamp": "2024-01-01T00:00:00+00:00",
      "last_timestamp": "2024-01-11T09:45:00+00:00",
      "first_close": 42715.45,
      "last_close": 24892.08,
      "candle_count": 1000,
      "checksum": "ecc9795a0940cb2c693e292b25d9fd4b"
    }
  }
}
```

### Per-Symbol Provenance

Each symbol gets tracked with:
- `first_timestamp` - First candle timestamp
- `last_timestamp` - Last candle timestamp
- `first_close` / `last_close` - Price range sanity check
- `candle_count` - Number of candles loaded
- `checksum` - MD5 hash of close prices for data verification

## Generating Sample Data

For testing/development, generate sample data:

```bash
# Generate core symbols (BTCUSDT, ETHUSDT, etc.)
python strategies/supply_demand_v1/data_loader.py

# Generate custom symbols
python -c "
from pathlib import Path
from strategies.supply_demand_v1.data_loader import generate_sample_historical_data

generate_sample_historical_data(
    Path('data'),
    ['AVAXUSDT', 'ADAUSDT', 'LINKUSDT'],
    timeframe='15m',
    num_candles=1000
)
"
```

## Obtaining Real Data

### From Binance (Free)

Download historical klines from Binance's public data service:

1. Visit: https://data.binance.vision/?prefix=data/futures/um/daily/klines/
2. Download ZIP files for your symbols/dates
3. Extract and convert to required CSV format

Example script:
```python
import pandas as pd
import zipfile

# Extract downloaded zip
with zipfile.ZipFile('BTCUSDT-15m-2024-01-01.zip', 'r') as zip_ref:
    zip_ref.extractall('.')

# Load and convert
df = pd.read_csv('BTCUSDT-15m-2024-01-01.csv', 
                 names=['timestamp', 'open', 'high', 'low', 'close', 
                        'volume', 'close_time', 'quote_vol', 'trades',
                        'taker_buy_vol', 'taker_buy_quote_vol', 'ignore'])

# Select required columns and format timestamp
df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

# Save
df.to_csv('data/binance_futures/BTCUSDT_15m.csv', index=False)
```

### From CCXT (Requires Installation)

If you have `ccxt` installed:

```python
import ccxt
import pandas as pd
from datetime import datetime

exchange = ccxt.binance({'enableRateLimit': True})
symbol = 'BTC/USDT'
timeframe = '15m'
since = exchange.parse8601('2024-01-01T00:00:00Z')

ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)

df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

df.to_csv('data/binance_futures/BTCUSDT_15m.csv', index=False)
```

## File Organization

Follow this directory structure:

```
data/
├── README.md
├── binance_futures/
│   ├── BTCUSDT_15m.csv
│   ├── ETHUSDT_15m.csv
│   ├── BNBUSDT_15m.csv
│   └── ...
├── bybit_futures/
│   └── SOLUSDT_15m.csv
└── binance_spot/
    └── BTCUSDT_1h.csv
```

### File Naming Convention

Pattern: `{symbol}_{timeframe}.csv`

- Symbol: Exchange format (e.g., `BTCUSDT` not `BTC/USDT`)
- Timeframe: `15m`, `1h`, `4h`, `1d`

## Configuration Examples

### Core Futures Config

```yaml
name: "sd_v1_futures_core"
description: "S&D V1 backtest on core futures/perpetual contracts"

# Use historical data
data_source: "historical"

historical_data:
  exchange: "binance"
  market_type: "futures"
  data_dir: "./data"

symbols:
  - "BTCUSDT"
  - "ETHUSDT"
  - "BNBUSDT"

start_date: "2024-01-01"
end_date: "2024-03-31"

timeframes:
  htf: "4h"
  itf: "1h"
  ltf: "15m"
  rtf: null

# ... rest of config
```

### Synthetic Config (Default)

```yaml
name: "sd_v1_default"
description: "Default S&D V1 backtest with synthetic data"

# data_source defaults to "synthetic" if not specified

symbols:
  - "BTC/USDT"
  - "ETH/USDT"

timeframes:
  htf: "4h"
  itf: "1h"
  ltf: "15m"
  rtf: null

data_generation:
  num_candles: 1000
  volatility: 0.02
  seed: 42

# ... rest of config
```

## Testing

Run the test suite to validate your setup:

```bash
# Test data loader
python -m pytest tests/test_data_loader.py -v

# Test runner integration
python -m pytest tests/test_runner_historical.py -v

# Test provenance tracking
python -m pytest tests/test_runner_provenance.py -v

# Run all tests
python -m pytest tests/ -v
```

## Troubleshooting

### "Historical data file not found"

Check:
1. File exists at expected path
2. Filename matches pattern: `{symbol}_{timeframe}.csv`
3. Directory structure: `{data_dir}/{exchange}_{market_type}/`

### "Insufficient candles"

Check:
1. CSV has enough rows (minimum 100)
2. Date range in CSV covers experiment start/end dates
3. Timestamps are within requested date range

### "Non-monotonic timestamps"

Check:
1. CSV is sorted by timestamp ascending
2. No duplicate timestamps
3. No gaps or missing data

### "Invalid price values"

Check:
1. All OHLC values are positive (> 0)
2. High >= Low for all candles
3. High >= Open, Close
4. Low <= Open, Close

## Performance Notes

- **CSV loading**: Fast for typical experiment sizes (&lt;10k candles per symbol)
- **Memory usage**: Minimal - candles loaded one symbol at a time
- **Validation overhead**: ~5-10ms per symbol (negligible)
- **Large datasets**: Consider filtering/downsampling before loading

## Migration Guide

### Existing configs continue to work unchanged

No action needed for existing synthetic configs!

### To migrate to historical data:

1. **Download/generate data** for your symbols
2. **Add 3 lines** to config:
   ```yaml
   data_source: "historical"
   historical_data:
     exchange: "binance"
     market_type: "futures"
     data_dir: "./data"
   ```
3. **Remove `data_generation` section** (no longer used)
4. **Verify** by running experiment

## Best Practices

1. **Always validate data quality** before running long backtests
2. **Use checksums** to verify data hasn't changed between runs
3. **Document data sources** in experiment configs (add comments)
4. **Version control configs**, not CSV files (too large)
5. **Regenerate sample data** from script (don't commit to git)
6. **Use real data for production** backtests (sample data is synthetic)

## Support

For issues or questions:
- Check `data/README.md` for data format details
- Review test files for usage examples
- See error messages for specific guidance
- Open issue if data loader has bugs
