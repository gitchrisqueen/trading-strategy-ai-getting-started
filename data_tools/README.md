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

**Update** - Fetch latest candles via CCXT:
```bash
python data_tools/binance_usdm_ohlcv.py update \
  --symbols BTCUSDT ETHUSDT \
  --timeframes 15m 1h 4h \
  --out ./data/binance_futures
```

### validate_ohlcv.py

Validate OHLCV CSV files for integrity.

```bash
python data_tools/validate_ohlcv.py \
  ./data/binance_futures/*.csv \
  --timeframe 15m \
  --verbose
```

**Checks:**
- Monotonic timestamps (strictly increasing)
- No duplicates
- Expected interval spacing
- Gap detection
- Valid OHLC relationships
- Positive prices and volumes

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
