# Historical Futures Data

This directory contains historical candle data for USDT-margined perpetual futures contracts.

## Directory Structure

```
data/
└── binance_futures/
    ├── BTCUSDT_15m.csv
    ├── ETHUSDT_15m.csv
    └── ...
```

## CSV Format

Each CSV file contains OHLCV candle data with the following columns:

```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234567.89
2024-01-01 00:15:00,42300.0,42800.0,42100.0,42600.0,2345678.90
...
```

### Column Descriptions

- **timestamp**: Candle timestamp in format `YYYY-MM-DD HH:MM:SS` (UTC)
- **open**: Opening price
- **high**: Highest price during period
- **low**: Lowest price during period
- **close**: Closing price
- **volume**: Trading volume

## Generating Sample Data

To generate sample historical data for testing:

```bash
python strategies/supply_demand_v1/data_loader.py
```

This creates synthetic but realistic candle data for the core futures symbols:
- BTCUSDT
- ETHUSDT
- BNBUSDT
- SOLUSDT
- XRPUSDT

## Using Real Historical Data

To use real historical data from exchanges:

### Option 1: Download from Binance

Use Binance's public data service to download historical klines:

```bash
# Example: Download BTCUSDT 15m klines for Jan 2024
wget "https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/15m/BTCUSDT-15m-2024-01-01.zip"
unzip BTCUSDT-15m-2024-01-01.zip
# Process and convert to required CSV format
```

### Option 2: Use CCXT (if available)

```python
import ccxt
import pandas as pd

exchange = ccxt.binance({'enableRateLimit': True})
exchange.load_markets()

# Fetch OHLCV data
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '15m', since=...)

# Convert to DataFrame and save
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.to_csv('data/binance_futures/BTCUSDT_15m.csv', index=False)
```

### Option 3: Use TradingStrategy.ai

If you have access to TradingStrategy.ai datasets:

```python
from tradingstrategy.client import Client
from tradingstrategy.timebucket import TimeBucket

client = Client.create_jupyter_client()
candles_df = client.fetch_candles_by_pair_ids(..., TimeBucket.m15)
# Process and save to CSV
```

## Configuration

To use historical data in experiments, set `data_source: "historical"` in your YAML config:

```yaml
# Data source: "synthetic" or "historical"
data_source: "historical"

# Historical data configuration
historical_data:
  exchange: "binance"
  market_type: "futures"
  data_dir: "./data"

symbols:
  - "BTCUSDT"
  - "ETHUSDT"

start_date: "2024-01-01"
end_date: "2024-03-31"
```

## File Naming Convention

Files must follow this naming pattern:

```
{exchange}_{market_type}/{symbol}_{timeframe}.csv
```

Examples:
- `binance_futures/BTCUSDT_15m.csv`
- `binance_futures/ETHUSDT_1h.csv`
- `bybit_futures/SOLUSDT_4h.csv`

## Data Quality Requirements

Historical data files must meet these requirements:

1. **Minimum candles**: At least 100 candles (configurable)
2. **Monotonic timestamps**: Timestamps must strictly increase
3. **Positive values**: All OHLC values must be > 0
4. **Complete OHLCV**: All required columns present
5. **Date range**: Sufficient coverage for experiment start/end dates

The runner will validate these requirements and fail loudly if data is invalid.

## Regenerating Sample Data

Sample data files are excluded from git (see `.gitignore`). To regenerate:

```bash
# Generate core symbols
python strategies/supply_demand_v1/data_loader.py

# Generate additional symbols
python -c "
from pathlib import Path
from strategies.supply_demand_v1.data_loader import generate_sample_historical_data

generate_sample_historical_data(
    Path('data'),
    ['AVAXUSDT', 'ADAUSDT', 'LINKUSDT', 'DOGEUSDT', 'MATICUSDT'],
    timeframe='15m',
    num_candles=1000
)
"
```

## Notes

- Sample data is synthetic and should only be used for testing/development
- For production backtesting, use real historical data from exchanges
- CSV files are excluded from git to keep repository size manageable
- Each symbol should have its own CSV file per timeframe
