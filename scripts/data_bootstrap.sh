#!/bin/bash
# Bootstrap historical data for core futures symbols
# This script downloads bulk historical data from Binance Vision

set -e

echo "=================================================="
echo "Bootstrapping Core Futures Data"
echo "=================================================="
echo ""

# Configuration
SYMBOLS="BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT"
TIMEFRAMES="15m 1h 4h"
START_DATE="2023-01-01"
END_DATE="2024-12-31"
OUTPUT_DIR="./data/binance_futures"

echo "Symbols: $SYMBOLS"
echo "Timeframes: $TIMEFRAMES"
echo "Date range: $START_DATE to $END_DATE"
echo "Output: $OUTPUT_DIR"
echo ""

# Run bootstrap
python data_tools/binance_usdm_ohlcv.py bootstrap \
  --symbols $SYMBOLS \
  --timeframes $TIMEFRAMES \
  --start $START_DATE \
  --end $END_DATE \
  --out $OUTPUT_DIR

echo ""
echo "=================================================="
echo "Bootstrap Complete"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Validate data: make data-validate"
echo "  2. Run backtest: python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml"
