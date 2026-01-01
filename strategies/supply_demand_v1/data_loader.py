"""Data loader for historical futures candles

This module provides functionality to load real historical candle data
for USDT-margined perpetual futures contracts. It supports loading from
CSV files in standard OHLCV format.

CSV Format Expected (accepts either 'timestamp' or 'datetime' column):
    timestamp,open,high,low,close,volume
    2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234.56
    ...
    
    OR
    
    datetime,open,high,low,close,volume
    2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234.56
    ...

Functions:
    load_historical_candles: Load candles from CSV file
    validate_candles: Validate candle data integrity
    generate_sample_historical_data: Generate sample CSV for testing
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import hashlib


class HistoricalDataError(Exception):
    """Raised when historical data cannot be loaded or is invalid"""
    pass


def parse_timestamp(ts_str: str) -> datetime:
    """Parse timestamp string to datetime with UTC timezone
    
    Supports multiple formats:
    - ISO format: 2024-01-01T00:00:00Z or 2024-01-01T00:00:00+00:00
    - Space separated: 2024-01-01 00:00:00
    - Unix timestamp: 1704067200000 (milliseconds)
    
    Args:
        ts_str: Timestamp string
    
    Returns:
        datetime with UTC timezone
    """
    # Try Unix timestamp (milliseconds)
    try:
        ts_int = int(ts_str)
        return datetime.fromtimestamp(ts_int / 1000, tz=timezone.utc)
    except (ValueError, OverflowError):
        pass
    
    # Try ISO format
    try:
        # Handle ISO format with Z or +00:00
        ts_clean = ts_str.replace('Z', '+00:00')
        if '+' not in ts_clean and ts_clean.count(':') == 2:
            # Add timezone if missing
            ts_clean = ts_clean + '+00:00'
        dt = datetime.fromisoformat(ts_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    
    # Try space-separated format
    try:
        dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def validate_candles(
    candles: List[Dict[str, Any]],
    symbol: str,
    min_candles: int = 100
) -> None:
    """Validate candle data integrity
    
    Checks:
    - Minimum candle count
    - Required fields present
    - Timestamps are monotonic increasing
    - Price/volume values are positive
    
    Args:
        candles: List of candle dictionaries
        symbol: Symbol name for error messages
        min_candles: Minimum number of candles required
    
    Raises:
        HistoricalDataError: If validation fails
    """
    if not candles:
        raise HistoricalDataError(
            f"No candles loaded for {symbol}. "
            f"Historical data file may be empty or missing."
        )
    
    if len(candles) < min_candles:
        raise HistoricalDataError(
            f"Insufficient candles for {symbol}: got {len(candles)}, "
            f"minimum required is {min_candles}. "
            f"Ensure historical data covers the requested date range."
        )
    
    # Check required fields
    required_fields = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
    for i, candle in enumerate(candles[:5]):  # Check first 5 candles
        for field in required_fields:
            if field not in candle:
                raise HistoricalDataError(
                    f"Candle {i} for {symbol} missing required field: {field}"
                )
    
    # Check timestamps are monotonic
    for i in range(1, len(candles)):
        if candles[i]['timestamp'] <= candles[i-1]['timestamp']:
            raise HistoricalDataError(
                f"Non-monotonic timestamps detected for {symbol} at index {i}. "
                f"Timestamps must be strictly increasing. "
                f"Previous: {candles[i-1]['timestamp']}, Current: {candles[i]['timestamp']}"
            )
    
    # Check price/volume are positive
    for i in range(min(10, len(candles))):  # Check first 10 candles
        candle = candles[i]
        if any(candle[f] <= 0 for f in ['open', 'high', 'low', 'close']):
            raise HistoricalDataError(
                f"Invalid price values in candle {i} for {symbol}: "
                f"All OHLC values must be positive"
            )
        if candle.get('volume', 0) < 0:
            raise HistoricalDataError(
                f"Invalid volume in candle {i} for {symbol}: "
                f"Volume cannot be negative"
            )


def load_historical_candles(
    symbol: str,
    timeframe: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    data_dir: Path = Path("./data"),
    exchange: str = "binance",
    market_type: str = "futures",
    return_metadata: bool = False
) -> Any:
    """Load historical candles from CSV file
    
    Expected file structure:
        {data_dir}/{exchange}_{market_type}/{symbol}_{timeframe}.csv
    
    Example:
        ./data/binance_futures/BTCUSDT_15m.csv
    
    CSV format (with header, accepts 'timestamp' or 'datetime'):
        timestamp,open,high,low,close,volume
        2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234.56
        
        OR
        
        datetime,open,high,low,close,volume
        2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234.56
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe: Candle timeframe (e.g., "15m", "1h", "4h")
        start_date: Start date (ISO format: "2024-01-01"), if None loads all
        end_date: End date (ISO format: "2024-03-31"), if None loads all
        data_dir: Root data directory
        exchange: Exchange name (default: "binance")
        market_type: Market type (default: "futures")
        return_metadata: If True, returns (candles, metadata) tuple
    
    Returns:
        If return_metadata=False: List of candle dictionaries
        If return_metadata=True: Tuple of (candles, metadata_dict)
        
        Metadata dict contains:
            - available_first_ts, available_last_ts, available_count
            - used_first_ts, used_last_ts, used_count
            - file_path
    
    Raises:
        HistoricalDataError: If file not found or data is invalid
    """
    # Construct file path
    subdir = f"{exchange}_{market_type}"
    filename = f"{symbol}_{timeframe}.csv"
    file_path = data_dir / subdir / filename
    
    if not file_path.exists():
        raise HistoricalDataError(
            f"Historical data file not found: {file_path}\n"
            f"Expected location: {data_dir}/{subdir}/{filename}\n"
            f"Please ensure historical data is downloaded and placed in the correct location."
        )
    
    # Parse date range (None means no filtering)
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HistoricalDataError(
                f"Invalid start_date format. Expected ISO format (YYYY-MM-DD): {e}"
            )
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HistoricalDataError(
                f"Invalid end_date format. Expected ISO format (YYYY-MM-DD): {e}"
            )
    
    # Load and parse CSV (first pass: load ALL candles to get available window)
    all_candles = []
    filtered_candles = []
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            
            # Validate header
            if reader.fieldnames is None:
                raise HistoricalDataError(
                    f"CSV file has no header: {file_path}"
                )
            
            # Accept either 'timestamp' or 'datetime' for the date column
            date_col = None
            if 'timestamp' in reader.fieldnames:
                date_col = 'timestamp'
            elif 'datetime' in reader.fieldnames:
                date_col = 'datetime'
            else:
                raise HistoricalDataError(
                    f"CSV file missing date column (need 'timestamp' or 'datetime')\n"
                    f"Found columns: {reader.fieldnames}\n"
                    f"Expected one of: timestamp, datetime"
                )
            
            required_cols = {'open', 'high', 'low', 'close', 'volume'}
            missing_cols = required_cols - set(reader.fieldnames)
            if missing_cols:
                raise HistoricalDataError(
                    f"CSV file missing required columns: {missing_cols}\n"
                    f"Found columns: {reader.fieldnames}\n"
                    f"Expected columns: {required_cols} + (timestamp or datetime)"
                )
            
            for row in reader:
                try:
                    # Parse timestamp (use whichever column is present)
                    ts = parse_timestamp(row[date_col])
                    
                    # Parse OHLCV
                    candle = {
                        'timestamp': ts,
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']),
                        'symbol': symbol,
                    }
                    all_candles.append(candle)
                    
                    # Also track filtered candles if date range specified
                    if start_dt and ts < start_dt:
                        continue
                    if end_dt and ts > end_dt:
                        continue
                    
                    filtered_candles.append(candle)
                    
                except (ValueError, KeyError) as e:
                    # Skip malformed rows but log warning
                    print(f"Warning: Skipping malformed row in {file_path}: {e}")
                    continue
    
    except FileNotFoundError:
        raise HistoricalDataError(
            f"Historical data file not found: {file_path}"
        )
    except Exception as e:
        raise HistoricalDataError(
            f"Error reading historical data from {file_path}: {e}"
        )
    
    # Choose which candles to return/validate
    candles_to_use = filtered_candles if (start_dt or end_dt) else all_candles
    
    # Validate loaded candles
    validate_candles(candles_to_use, symbol, min_candles=100)
    
    # Build metadata if requested
    if return_metadata:
        metadata = {
            'file_path': str(file_path),
            'available_count': len(all_candles),
            'used_count': len(candles_to_use),
        }
        
        if all_candles:
            metadata['available_first_ts'] = all_candles[0]['timestamp'].isoformat()
            metadata['available_last_ts'] = all_candles[-1]['timestamp'].isoformat()
        else:
            metadata['available_first_ts'] = None
            metadata['available_last_ts'] = None
            
        if candles_to_use:
            metadata['used_first_ts'] = candles_to_use[0]['timestamp'].isoformat()
            metadata['used_last_ts'] = candles_to_use[-1]['timestamp'].isoformat()
        else:
            metadata['used_first_ts'] = None
            metadata['used_last_ts'] = None
        
        return candles_to_use, metadata
    
    return candles_to_use


def find_common_window(
    symbol: str,
    timeframes: List[str],
    data_dir: Path,
    exchange: str = "binance",
    market_type: str = "futures"
) -> Tuple[Optional[str], Optional[str]]:
    """Find the common overlapping time window across multiple timeframes
    
    Useful when use_full_history=true to determine the maximum window
    that has data available for all required timeframes.
    
    Args:
        symbol: Trading symbol
        timeframes: List of timeframes to check (e.g., ["15m", "1h", "4h"])
        data_dir: Root data directory
        exchange: Exchange name
        market_type: Market type
    
    Returns:
        Tuple of (start_date, end_date) in ISO format, or (None, None) if no overlap
    
    Raises:
        HistoricalDataError: If any required file is missing
    """
    if not timeframes:
        return None, None
    
    # Load metadata for each timeframe
    all_metadata = []
    for tf in timeframes:
        try:
            _, metadata = load_historical_candles(
                symbol=symbol,
                timeframe=tf,
                start_date=None,
                end_date=None,
                data_dir=data_dir,
                exchange=exchange,
                market_type=market_type,
                return_metadata=True
            )
            all_metadata.append(metadata)
        except HistoricalDataError:
            # If any timeframe is missing, we can't determine common window
            raise
    
    # Find the latest start and earliest end across all timeframes
    start_dates = []
    end_dates = []
    
    for metadata in all_metadata:
        if metadata['available_first_ts']:
            start_dates.append(datetime.fromisoformat(metadata['available_first_ts']))
        if metadata['available_last_ts']:
            end_dates.append(datetime.fromisoformat(metadata['available_last_ts']))
    
    if not start_dates or not end_dates:
        return None, None
    
    # Common window is: max(all_starts) to min(all_ends)
    common_start = max(start_dates)
    common_end = min(end_dates)
    
    # Check if there's actually overlap
    if common_start > common_end:
        return None, None
    
    # Return as ISO date strings (date only, not datetime)
    return common_start.date().isoformat(), common_end.date().isoformat()


def generate_sample_historical_data(
    output_dir: Path,
    symbols: List[str],
    timeframe: str = "15m",
    num_candles: int = 1000,
    exchange: str = "binance",
    market_type: str = "futures"
) -> None:
    """Generate sample historical data CSV files for testing
    
    Creates realistic synthetic data in the expected CSV format.
    Useful for CI testing and development when real data is unavailable.
    
    Args:
        output_dir: Root output directory
        symbols: List of symbols to generate
        timeframe: Candle timeframe
        num_candles: Number of candles to generate per symbol
        exchange: Exchange name
        market_type: Market type
    """
    import random
    from datetime import timedelta
    
    subdir = output_dir / f"{exchange}_{market_type}"
    subdir.mkdir(parents=True, exist_ok=True)
    
    # Base prices for different symbols
    base_prices = {
        'BTCUSDT': 42000.0,
        'ETHUSDT': 2500.0,
        'BNBUSDT': 300.0,
        'SOLUSDT': 100.0,
        'XRPUSDT': 0.60,
        'AVAXUSDT': 35.0,
        'ADAUSDT': 0.50,
        'LINKUSDT': 15.0,
        'DOGEUSDT': 0.08,
        'MATICUSDT': 0.90,
    }
    
    for symbol in symbols:
        filename = f"{symbol}_{timeframe}.csv"
        file_path = subdir / filename
        
        base_price = base_prices.get(symbol, 100.0)
        current_price = base_price
        
        # Start from 2024-01-01
        timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        
        # Determine time delta based on timeframe
        if timeframe == '15m':
            delta = timedelta(minutes=15)
        elif timeframe == '1h':
            delta = timedelta(hours=1)
        elif timeframe == '4h':
            delta = timedelta(hours=4)
        elif timeframe == '1d':
            delta = timedelta(days=1)
        else:
            delta = timedelta(minutes=15)  # Default
        
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            for _ in range(num_candles):
                # Random walk with volatility
                volatility = 0.02
                price_change = random.gauss(0, volatility)
                
                open_price = current_price
                close_price = open_price * (1 + price_change)
                
                # Generate high/low with wicks
                wick_size = abs(price_change) * random.uniform(0.3, 0.7)
                if close_price > open_price:
                    high = close_price * (1 + wick_size)
                    low = open_price * (1 - wick_size)
                else:
                    high = open_price * (1 + wick_size)
                    low = close_price * (1 - wick_size)
                
                volume = random.uniform(100000, 1000000)
                
                writer.writerow([
                    timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    f"{open_price:.2f}",
                    f"{high:.2f}",
                    f"{low:.2f}",
                    f"{close_price:.2f}",
                    f"{volume:.2f}"
                ])
                
                current_price = close_price
                timestamp += delta
        
        print(f"Generated sample data: {file_path}")


if __name__ == "__main__":
    # Generate sample data for testing
    output_dir = Path(__file__).parent.parent.parent / 'data'
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
    
    print(f"Generating sample historical data in {output_dir}...")
    generate_sample_historical_data(
        output_dir,
        symbols,
        timeframe='15m',
        num_candles=1000
    )
    print("Done!")
