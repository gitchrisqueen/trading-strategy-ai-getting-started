# Data Tools

Tools for downloading and managing historical OHLCV data for backtesting.

## Tools

### binance_usdm_ohlcv.py

Download and update Binance USDT-M perpetual futures data.

**Bootstrap** - Download bulk historical data:
```bash
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols BTCUSDT ETHUSDT \
  --timeframes 15m 1h 4h \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --out ./data/binance_futures
```

**Note**: The tool automatically handles Binance Vision CSV files with or without header rows.

**Update** - Fetch latest candles via CCXT:
```bash
python data_tools/binance_usdm_ohlcv.py update \
  --symbols BTCUSDT ETHUSDT \
  --timeframes 15m 1h 4h \
  --out ./data/binance_futures
```

### validate_ohlcv.py

Validate OHLCV CSV files for integrity. **Automatically detects timeframe from filename.**

**Auto-detect timeframes** (recommended):
```bash
# Validates all files, inferring timeframe from filename
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv
```

**Filter by specific timeframe**:
```bash
# Only validates 1h files
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --timeframe 1h
```

**Allow gap tolerance**:
```bash
# Allow up to 2 missing intervals
python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --max-gap-intervals 2
```

**Checks:**
- Monotonic timestamps (strictly increasing)
- No duplicates
- Expected interval spacing (per timeframe)
- Gap detection
- Valid OHLC relationships
- Positive prices and volumes

**Timeframe Detection:**
- Automatically extracts timeframe from filename (e.g., `BTCUSDT_15m.csv` → `15m`)
- Validates each file with its correct interval (no more false gaps!)
- Supports: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w

## Quick Start

Use convenience scripts:

```bash
# Bootstrap core symbols
make data-bootstrap

# Update data
make data-update

# Validate data
make data-validate
```

## Documentation

See [docs/DATA_PIPELINE.md](../docs/DATA_PIPELINE.md) for complete usage guide.
