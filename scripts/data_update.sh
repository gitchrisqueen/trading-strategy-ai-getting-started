#!/bin/bash
# Update existing data with latest candles via CCXT
# This script fetches new candles and appends them to existing CSV files

set -e

echo "=================================================="
echo "Updating Futures Data"
echo "=================================================="
echo ""

# Configuration
SYMBOLS="BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT"
TIMEFRAMES="15m 1h 4h"
OUTPUT_DIR="./data/binance_futures"

echo "Symbols: $SYMBOLS"
echo "Timeframes: $TIMEFRAMES"
echo "Output: $OUTPUT_DIR"
echo ""

# Check if data exists
if [ ! -d "$OUTPUT_DIR" ] || [ -z "$(ls -A $OUTPUT_DIR/*.csv 2>/dev/null)" ]; then
  echo "Error: No existing data found in $OUTPUT_DIR"
  echo "Run bootstrap first: make data-bootstrap"
  exit 1
fi

# Run update
python data_tools/binance_usdm_ohlcv.py update \
  --symbols $SYMBOLS \
  --timeframes $TIMEFRAMES \
  --out $OUTPUT_DIR

echo ""
echo "=================================================="
echo "Update Complete"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Validate data: make data-validate"
echo "  2. Run backtest: python scripts/run_supply_demand_v1.py --config experiments/sd_v1_futures_core.yaml"
