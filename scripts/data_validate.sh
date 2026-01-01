#!/bin/bash
# Validate OHLCV data files for integrity
# Checks for gaps, duplicates, and invalid data

set -e

echo "=================================================="
echo "Validating Futures Data"
echo "=================================================="
echo ""

# Configuration
DATA_DIR="./data/binance_futures"
TIMEFRAME="15m"

if [ ! -d "$DATA_DIR" ]; then
  echo "Error: Data directory not found: $DATA_DIR"
  echo "Run bootstrap first: make data-bootstrap"
  exit 1
fi

# Count CSV files
CSV_COUNT=$(ls -1 $DATA_DIR/*.csv 2>/dev/null | wc -l)

if [ "$CSV_COUNT" -eq 0 ]; then
  echo "Error: No CSV files found in $DATA_DIR"
  echo "Run bootstrap first: make data-bootstrap"
  exit 1
fi

echo "Validating $CSV_COUNT files in $DATA_DIR"
echo "Timeframe: $TIMEFRAME"
echo ""

# Run validation
python data_tools/validate_ohlcv.py \
  $DATA_DIR/*.csv \
  --timeframe $TIMEFRAME \
  --verbose

echo ""
