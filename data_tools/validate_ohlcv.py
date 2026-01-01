#!/usr/bin/env python
"""OHLCV Data Validation Tool

Validates OHLCV CSV files for:
- Monotonic timestamps (strictly increasing)
- No duplicates
- Expected interval spacing per timeframe
- Gap detection (missing data)
- Valid OHLC relationships (high >= low, etc.)

Returns exit code 0 on success, non-zero on validation failure.

Usage:
  # Validate files with auto-detected timeframes
  python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv

  # Validate single file (timeframe inferred from filename)
  python data_tools/validate_ohlcv.py ./data/binance_futures/BTCUSDT_15m.csv

  # Validate only 1h files explicitly
  python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --timeframe 1h

  # Allow small gaps (up to 2 missing intervals)
  python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --max-gap-intervals 2

  # Verbose output with all errors
  python data_tools/validate_ohlcv.py ./data/binance_futures/*.csv --verbose
"""

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


# Timeframe to expected interval mapping
TIMEFRAME_INTERVALS = {
    '1m': timedelta(minutes=1),
    '3m': timedelta(minutes=3),
    '5m': timedelta(minutes=5),
    '15m': timedelta(minutes=15),
    '30m': timedelta(minutes=30),
    '1h': timedelta(hours=1),
    '2h': timedelta(hours=2),
    '4h': timedelta(hours=4),
    '6h': timedelta(hours=6),
    '8h': timedelta(hours=8),
    '12h': timedelta(hours=12),
    '1d': timedelta(days=1),
    '3d': timedelta(days=3),
    '1w': timedelta(weeks=1),
}


class ValidationError:
    """Represents a single validation error"""
    def __init__(self, error_type: str, row_num: int, message: str, details: Dict[str, Any] = None):
        self.error_type = error_type
        self.row_num = row_num
        self.message = message
        self.details = details or {}
    
    def __str__(self):
        details_str = ', '.join(f"{k}={v}" for k, v in self.details.items())
        return f"[Row {self.row_num}] {self.error_type}: {self.message} ({details_str})"


class ValidationResult:
    """Aggregated validation results"""
    def __init__(self, file_path: Path, timeframe: Optional[str] = None):
        self.file_path = file_path
        self.timeframe = timeframe
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []
        self.total_rows = 0
        self.duplicate_count = 0
        self.gap_count = 0
    
    def add_error(self, error: ValidationError):
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
    
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def summary(self) -> str:
        timeframe_str = f" [{self.timeframe}]" if self.timeframe else ""
        if self.is_valid():
            return f"✓ {self.file_path.name}{timeframe_str}: PASS ({self.total_rows} rows)"
        else:
            return f"✗ {self.file_path.name}{timeframe_str}: FAIL ({len(self.errors)} errors)"


def parse_timestamp(ts_str: str) -> datetime:
    """Parse timestamp string to datetime"""
    # Try multiple formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%f',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    
    # Try with timezone
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def extract_timeframe_from_filename(file_path: Path) -> Optional[str]:
    """Extract timeframe from filename pattern {SYMBOL}_{TIMEFRAME}.csv
    
    Args:
        file_path: Path to CSV file
    
    Returns:
        Timeframe string (e.g., '15m', '1h', '4h') or None if not found
    
    Examples:
        BTCUSDT_15m.csv -> 15m
        ETHUSDT_1h.csv -> 1h
        BNBUSDT_4h.csv -> 4h
    """
    # Get filename without extension
    filename = file_path.stem
    
    # Try to extract timeframe after last underscore
    parts = filename.split('_')
    if len(parts) >= 2:
        potential_tf = parts[-1].lower()
        
        # Check if it matches a known timeframe
        if potential_tf in TIMEFRAME_INTERVALS:
            return potential_tf
    
    return None


def validate_ohlc_relationships(row: Dict[str, Any], row_num: int) -> List[ValidationError]:
    """Validate OHLC price relationships"""
    errors = []
    
    try:
        open_price = float(row['open'])
        high = float(row['high'])
        low = float(row['low'])
        close = float(row['close'])
        volume = float(row.get('volume', 0))
    except (ValueError, KeyError) as e:
        errors.append(ValidationError(
            'INVALID_PRICE',
            row_num,
            f"Cannot parse prices: {e}",
            {'row': row}
        ))
        return errors
    
    # Check all prices are positive
    if open_price <= 0 or high <= 0 or low <= 0 or close <= 0:
        errors.append(ValidationError(
            'NEGATIVE_PRICE',
            row_num,
            "Prices must be positive",
            {'open': open_price, 'high': high, 'low': low, 'close': close}
        ))
    
    # Check high >= low
    if high < low:
        errors.append(ValidationError(
            'HIGH_LOW_INVALID',
            row_num,
            "High must be >= Low",
            {'high': high, 'low': low}
        ))
    
    # Check high >= open, close
    if high < open_price or high < close:
        errors.append(ValidationError(
            'HIGH_INVALID',
            row_num,
            "High must be >= Open and Close",
            {'high': high, 'open': open_price, 'close': close}
        ))
    
    # Check low <= open, close
    if low > open_price or low > close:
        errors.append(ValidationError(
            'LOW_INVALID',
            row_num,
            "Low must be <= Open and Close",
            {'low': low, 'open': open_price, 'close': close}
        ))
    
    # Check volume is non-negative
    if volume < 0:
        errors.append(ValidationError(
            'NEGATIVE_VOLUME',
            row_num,
            "Volume cannot be negative",
            {'volume': volume}
        ))
    
    return errors


def validate_csv_file(
    file_path: Path,
    timeframe: Optional[str] = None,
    max_gap_intervals: int = 0
) -> ValidationResult:
    """Validate a single OHLCV CSV file
    
    Args:
        file_path: Path to CSV file
        timeframe: Expected timeframe (e.g., '15m', '1h'). If None, will try to infer from filename.
        max_gap_intervals: Allow gaps up to this many intervals (default: 0 = no tolerance)
    
    Returns:
        ValidationResult with errors and warnings
    """
    # Try to infer timeframe from filename if not provided
    inferred_timeframe = None
    if timeframe is None:
        inferred_timeframe = extract_timeframe_from_filename(file_path)
        timeframe = inferred_timeframe
    
    result = ValidationResult(file_path, timeframe=timeframe)
    
    # Check file exists
    if not file_path.exists():
        result.add_error(ValidationError(
            'FILE_NOT_FOUND',
            0,
            f"File not found: {file_path}"
        ))
        return result
    
    # Read CSV
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            
            # Validate header
            if reader.fieldnames is None:
                result.add_error(ValidationError(
                    'NO_HEADER',
                    0,
                    "CSV file has no header"
                ))
                return result
            
            # Accept either 'datetime' or 'timestamp' for date column
            has_datetime = 'datetime' in reader.fieldnames
            has_timestamp = 'timestamp' in reader.fieldnames
            
            if not (has_datetime or has_timestamp):
                result.add_error(ValidationError(
                    'MISSING_COLUMNS',
                    0,
                    "Missing required date column: need either 'datetime' or 'timestamp'"
                ))
                return result
            
            # Use whichever date column exists
            date_col = 'datetime' if has_datetime else 'timestamp'
            
            required_cols = {'open', 'high', 'low', 'close', 'volume'}
            missing_cols = required_cols - set(reader.fieldnames)
            if missing_cols:
                result.add_error(ValidationError(
                    'MISSING_COLUMNS',
                    0,
                    f"Missing required columns: {missing_cols}"
                ))
                return result
            
            # Parse all rows
            rows = []
            timestamps_seen = set()
            
            for i, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                result.total_rows += 1
                
                # Parse timestamp
                try:
                    ts = parse_timestamp(row[date_col])
                except ValueError as e:
                    result.add_error(ValidationError(
                        'INVALID_TIMESTAMP',
                        i,
                        str(e),
                        {date_col: row[date_col]}
                    ))
                    continue
                
                # Check for duplicates
                ts_str = row[date_col]
                if ts_str in timestamps_seen:
                    result.add_error(ValidationError(
                        'DUPLICATE_TIMESTAMP',
                        i,
                        f"Duplicate timestamp: {ts_str}"
                    ))
                    result.duplicate_count += 1
                    continue
                
                timestamps_seen.add(ts_str)
                
                # Validate OHLC relationships
                ohlc_errors = validate_ohlc_relationships(row, i)
                for error in ohlc_errors:
                    result.add_error(error)
                
                rows.append((i, ts, row))
            
            if not rows:
                result.add_error(ValidationError(
                    'EMPTY_FILE',
                    0,
                    "No valid rows in file"
                ))
                return result
            
            # Check monotonic timestamps
            prev_row_num, prev_ts, prev_row = rows[0]
            for row_num, ts, row in rows[1:]:
                if ts <= prev_ts:
                    result.add_error(ValidationError(
                        'NON_MONOTONIC',
                        row_num,
                        f"Timestamp {ts} is not greater than previous {prev_ts}"
                    ))
                
                prev_row_num = row_num
                prev_ts = ts
                prev_row = row
            
            # Check interval spacing and gaps (if timeframe provided or inferred)
            if timeframe:
                expected_interval = TIMEFRAME_INTERVALS.get(timeframe)
                if not expected_interval:
                    result.add_warning(f"Unknown timeframe: {timeframe}. Skipping gap detection.")
                else:
                    if inferred_timeframe:
                        result.add_warning(f"Inferred timeframe: {inferred_timeframe}")
                    
                    # Check gaps
                    prev_row_num, prev_ts, _ = rows[0]
                    for row_num, ts, _ in rows[1:]:
                        actual_interval = ts - prev_ts
                        
                        # Allow some tolerance (e.g., 1 second for rounding)
                        if actual_interval > expected_interval + timedelta(seconds=1):
                            # Calculate how many intervals are missing
                            missing_intervals = int(actual_interval / expected_interval) - 1
                            
                            if missing_intervals > max_gap_intervals:
                                result.add_error(ValidationError(
                                    'GAP_DETECTED',
                                    row_num,
                                    f"Gap detected: {missing_intervals} intervals missing",
                                    {
                                        'prev_ts': prev_ts,
                                        'current_ts': ts,
                                        'expected_interval': str(expected_interval),
                                        'actual_interval': str(actual_interval),
                                        'missing_intervals': missing_intervals
                                    }
                                ))
                                result.gap_count += 1
                        
                        prev_row_num = row_num
                        prev_ts = ts
            else:
                result.add_warning("No timeframe provided or inferred. Skipping gap detection.")
    
    except Exception as e:
        result.add_error(ValidationError(
            'FILE_READ_ERROR',
            0,
            f"Error reading file: {e}"
        ))
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Validate OHLCV CSV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'files',
        nargs='+',
        help='CSV files to validate (supports wildcards)'
    )
    parser.add_argument(
        '--timeframe',
        help='Expected timeframe for gap detection (e.g., 15m, 1h, 4h). '
             'If not provided, will attempt to infer from filename. '
             'If provided, only validates files matching this timeframe.'
    )
    parser.add_argument(
        '--max-gap-intervals',
        type=int,
        default=0,
        help='Allow gaps up to this many intervals (default: 0 = strict, no tolerance)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show all errors and warnings'
    )
    
    args = parser.parse_args()
    
    # Validate all files
    results = []
    for file_pattern in args.files:
        # Handle wildcards
        file_paths = list(Path('.').glob(file_pattern))
        if not file_paths:
            # Try as direct path
            file_paths = [Path(file_pattern)]
        
        for file_path in file_paths:
            # If user specified a timeframe, check if file matches
            if args.timeframe:
                file_tf = extract_timeframe_from_filename(file_path)
                if file_tf and file_tf != args.timeframe:
                    # Skip files that don't match the requested timeframe
                    continue
            
            result = validate_csv_file(
                file_path,
                timeframe=args.timeframe,
                max_gap_intervals=args.max_gap_intervals
            )
            results.append(result)
    
    # Print results
    print("=" * 80)
    print("OHLCV Data Validation Report")
    print("=" * 80)
    print()
    
    total_files = len(results)
    valid_files = sum(1 for r in results if r.is_valid())
    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    
    for result in results:
        print(result.summary())
        
        if args.verbose:
            if result.warnings:
                print("  Warnings:")
                for warning in result.warnings:
                    print(f"    - {warning}")
            
            if result.errors:
                print("  Errors:")
                for error in result.errors[:10]:  # Limit to first 10
                    print(f"    - {error}")
                if len(result.errors) > 10:
                    print(f"    ... and {len(result.errors) - 10} more errors")
            
            print()
    
    print("=" * 80)
    print(f"Summary: {valid_files}/{total_files} files valid")
    print(f"  Total errors: {total_errors}")
    print(f"  Total warnings: {total_warnings}")
    print("=" * 80)
    
    # Exit with appropriate code
    if valid_files == total_files:
        print("\n✓ All files passed validation")
        sys.exit(0)
    else:
        print(f"\n✗ {total_files - valid_files} file(s) failed validation")
        sys.exit(1)


if __name__ == '__main__':
    main()
