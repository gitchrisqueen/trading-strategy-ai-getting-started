#!/usr/bin/env python
"""Binance USDT-M Perpetual Futures OHLCV Data Downloader

This tool provides automated data acquisition for Binance USDT-margined perpetual futures:
- Bootstrap: Download bulk historical data from data.binance.vision
- Update: Incremental updates via CCXT (binanceusdm)

Output files match the existing loader convention:
  ./data/binance_futures/{SYMBOL}_{TIMEFRAME}.csv

CSV Format:
  datetime,open,high,low,close,volume

Usage Examples:
  # Bootstrap historical data
  python data_tools/binance_usdm_ohlcv.py bootstrap \\
    --symbols BTCUSDT ETHUSDT \\
    --timeframes 15m 1h 4h \\
    --start 2023-01-01 \\
    --end 2024-12-31 \\
    --out ./data/binance_futures

  # Update with latest candles
  python data_tools/binance_usdm_ohlcv.py update \\
    --symbols BTCUSDT ETHUSDT \\
    --timeframes 15m 1h 4h \\
    --out ./data/binance_futures
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from io import BytesIO

import requests
import pandas as pd

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("Warning: ccxt not installed. Update command will not work.")
    print("Install with: pip install ccxt")


# Binance Vision base URL
BINANCE_VISION_BASE = "https://data.binance.vision/data/futures/um/daily/klines"

# Timeframe mapping: our format -> Binance format
TIMEFRAME_MAP = {
    '1m': '1m',
    '3m': '3m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '2h': '2h',
    '4h': '4h',
    '6h': '6h',
    '8h': '8h',
    '12h': '12h',
    '1d': '1d',
    '3d': '3d',
    '1w': '1w',
    '1M': '1M',
}

# Timeframe to timedelta mapping for incrementing
TIMEFRAME_DELTA = {
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


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime with UTC timezone"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected: YYYY-MM-DD")


def get_csv_path(output_dir: Path, symbol: str, timeframe: str) -> Path:
    """Get path to CSV file for symbol/timeframe"""
    filename = f"{symbol}_{timeframe}.csv"
    return output_dir / filename


def get_manifest_path(output_dir: Path) -> Path:
    """Get path to manifest file"""
    return output_dir / "_manifest.json"


def load_manifest(output_dir: Path) -> Dict[str, Any]:
    """Load manifest file if it exists"""
    manifest_path = get_manifest_path(output_dir)
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            return json.load(f)
    return {}


def save_manifest(output_dir: Path, manifest: Dict[str, Any]):
    """Save manifest file"""
    manifest_path = get_manifest_path(output_dir)
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)


def calculate_checksum(csv_path: Path) -> str:
    """Calculate MD5 checksum of CSV file close prices"""
    if not csv_path.exists():
        return ""
    
    close_prices = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            close_prices.append(row['close'])
    
    close_string = ','.join(close_prices)
    return hashlib.md5(close_string.encode()).hexdigest()


def read_last_timestamp(csv_path: Path) -> Optional[datetime]:
    """Read the last timestamp from a CSV file"""
    if not csv_path.exists():
        return None
    
    try:
        # Read last line efficiently
        with open(csv_path, 'rb') as f:
            # Seek to end
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            
            # Read last 1024 bytes (should be enough for last line)
            if file_size > 1024:
                f.seek(-1024, os.SEEK_END)
            else:
                f.seek(0)
            
            # Read and parse
            lines = f.read().decode('utf-8').strip().split('\n')
            if len(lines) < 2:  # Header + at least one row
                return None
            
            last_line = lines[-1]
            # Parse datetime (first column)
            ts_str = last_line.split(',')[0]
            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except Exception as e:
        print(f"Warning: Could not read last timestamp from {csv_path}: {e}")
        return None


def download_binance_vision_zip(
    symbol: str,
    timeframe: str,
    date: datetime,
    cache_dir: Path
) -> Optional[Path]:
    """Download a single day's data from Binance Vision
    
    Returns path to cached zip file, or None if download failed
    """
    # Convert timeframe
    binance_tf = TIMEFRAME_MAP.get(timeframe)
    if not binance_tf:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    
    # Construct URL
    date_str = date.strftime('%Y-%m-%d')
    filename = f"{symbol}-{binance_tf}-{date_str}.zip"
    url = f"{BINANCE_VISION_BASE}/{symbol}/{binance_tf}/{filename}"
    
    # Check cache
    cache_file = cache_dir / filename
    if cache_file.exists():
        return cache_file
    
    # Download
    print(f"Downloading {filename}...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Save to cache
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'wb') as f:
            f.write(response.content)
        
        return cache_file
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # Data doesn't exist for this date (future or missing)
            return None
        else:
            print(f"Error downloading {filename}: {e}")
            return None
    except Exception as e:
        print(f"Error downloading {filename}: {e}")
        return None


def parse_binance_vision_csv(zip_path: Path) -> List[Dict[str, Any]]:
    """Parse Binance Vision CSV from zip file
    
    Binance CSV format (may have header):
    timestamp,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_vol,taker_buy_quote_vol,ignore
    
    Or with header:
    open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_vol,taker_buy_quote_vol,ignore
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Should contain one CSV file
        csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
        if not csv_files:
            raise ValueError(f"No CSV file found in {zip_path}")
        
        csv_name = csv_files[0]
        with zf.open(csv_name) as f:
            content = f.read().decode('utf-8')
            
            candles = []
            lines = content.strip().split('\n')
            
            for i, line in enumerate(lines):
                if not line:
                    continue
                
                parts = line.split(',')
                if len(parts) < 11:
                    continue
                
                # Skip header row if present (check if first column is numeric)
                try:
                    ts_ms = int(parts[0])
                except ValueError:
                    # First column is not numeric, likely a header row
                    if i == 0 and ('time' in parts[0].lower() or 'open' in parts[0].lower()):
                        continue  # Skip header
                    else:
                        # Unknown format, skip this line
                        print(f"Warning: Skipping line {i+1} in {csv_name}: cannot parse timestamp")
                        continue
                
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                
                candle = {
                    'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'open': parts[1],
                    'high': parts[2],
                    'low': parts[3],
                    'close': parts[4],
                    'volume': parts[5],
                }
                candles.append(candle)
            
            return candles


def write_csv(csv_path: Path, candles: List[Dict[str, Any]], mode: str = 'w'):
    """Write candles to CSV file
    
    Args:
        csv_path: Path to CSV file
        candles: List of candle dictionaries
        mode: 'w' for write, 'a' for append
    """
    if not candles:
        return
    
    # Ensure parent directory exists
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = ['datetime', 'open', 'high', 'low', 'close', 'volume']
    
    write_header = (mode == 'w') or (not csv_path.exists())
    
    with open(csv_path, mode, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(candles)


def bootstrap_symbol(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    output_dir: Path,
    cache_dir: Path,
    force: bool = False
) -> bool:
    """Bootstrap historical data for a symbol/timeframe
    
    Returns True if successful, False otherwise
    """
    csv_path = get_csv_path(output_dir, symbol, timeframe)
    
    # Check if file exists and we're not forcing
    if csv_path.exists() and not force:
        print(f"Skipping {symbol}_{timeframe}: file exists (use --force to redownload)")
        return True
    
    print(f"\n{'='*60}")
    print(f"Bootstrapping {symbol} {timeframe}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"{'='*60}")
    
    all_candles = []
    current_date = start_date
    
    while current_date <= end_date:
        # Download zip for this date
        zip_path = download_binance_vision_zip(symbol, timeframe, current_date, cache_dir)
        
        if zip_path:
            try:
                # Parse candles
                candles = parse_binance_vision_csv(zip_path)
                all_candles.extend(candles)
                print(f"  Loaded {len(candles)} candles for {current_date.date()}")
            except Exception as e:
                print(f"  Error parsing {zip_path}: {e}")
        
        # Move to next day
        current_date += timedelta(days=1)
    
    if not all_candles:
        print(f"No data found for {symbol} {timeframe}")
        return False
    
    # Remove duplicates and sort by datetime
    print(f"Consolidating {len(all_candles)} candles...")
    df = pd.DataFrame(all_candles)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.drop_duplicates(subset=['datetime'])
    df = df.sort_values('datetime')
    df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Write to CSV
    write_csv(csv_path, df.to_dict('records'), mode='w')
    
    print(f"✓ Wrote {len(df)} candles to {csv_path}")
    
    # Update manifest
    manifest = load_manifest(output_dir)
    key = f"{symbol}_{timeframe}"
    manifest[key] = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'first_ts': df.iloc[0]['datetime'],
        'last_ts': df.iloc[-1]['datetime'],
        'candle_count': len(df),
        'checksum': calculate_checksum(csv_path),
    }
    save_manifest(output_dir, manifest)
    
    return True


def update_symbol(
    symbol: str,
    timeframe: str,
    output_dir: Path,
    limit: int = 1000
) -> bool:
    """Update symbol data with latest candles via CCXT
    
    Returns True if successful, False otherwise
    """
    if not CCXT_AVAILABLE:
        print("Error: ccxt not installed. Cannot update.")
        return False
    
    csv_path = get_csv_path(output_dir, symbol, timeframe)
    
    # Read last timestamp
    last_ts = read_last_timestamp(csv_path)
    
    if last_ts is None:
        print(f"No existing data for {symbol}_{timeframe}. Run bootstrap first.")
        return False
    
    print(f"\n{'='*60}")
    print(f"Updating {symbol} {timeframe}")
    print(f"Last timestamp: {last_ts}")
    print(f"{'='*60}")
    
    # Initialize CCXT exchange
    try:
        exchange = ccxt.binanceusdm({
            'enableRateLimit': True,
        })
    except Exception as e:
        print(f"Error initializing CCXT: {e}")
        return False
    
    # Fetch new candles
    try:
        # Convert symbol format: BTCUSDT -> BTC/USDT
        ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
        
        # Fetch candles since last timestamp
        since_ms = int(last_ts.timestamp() * 1000)
        
        print(f"Fetching candles since {last_ts}...")
        ohlcv = exchange.fetch_ohlcv(
            ccxt_symbol,
            timeframe=timeframe,
            since=since_ms,
            limit=limit
        )
        
        if not ohlcv:
            print("No new candles available")
            return True
        
        # Convert to our format
        new_candles = []
        for row in ohlcv:
            ts_ms, open_, high, low, close, volume = row
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            
            # Skip candles we already have
            if dt <= last_ts:
                continue
            
            candle = {
                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'open': str(open_),
                'high': str(high),
                'low': str(low),
                'close': str(close),
                'volume': str(volume),
            }
            new_candles.append(candle)
        
        if not new_candles:
            print("No new candles to append (all duplicates)")
            return True
        
        # Append to CSV
        write_csv(csv_path, new_candles, mode='a')
        
        print(f"✓ Appended {len(new_candles)} new candles")
        
        # Update manifest
        manifest = load_manifest(output_dir)
        key = f"{symbol}_{timeframe}"
        
        # Read updated counts
        df = pd.read_csv(csv_path)
        
        manifest[key] = {
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'first_ts': df.iloc[0]['datetime'],
            'last_ts': df.iloc[-1]['datetime'],
            'candle_count': len(df),
            'checksum': calculate_checksum(csv_path),
        }
        save_manifest(output_dir, manifest)
        
        return True
    
    except Exception as e:
        print(f"Error fetching candles: {e}")
        return False


def cmd_bootstrap(args):
    """Execute bootstrap command"""
    output_dir = Path(args.out)
    cache_dir = Path(args.cache)
    
    start_date = parse_date(args.start)
    end_date = parse_date(args.end)
    
    print(f"Bootstrap Configuration:")
    print(f"  Symbols: {', '.join(args.symbols)}")
    print(f"  Timeframes: {', '.join(args.timeframes)}")
    print(f"  Date range: {start_date.date()} to {end_date.date()}")
    print(f"  Output dir: {output_dir}")
    print(f"  Cache dir: {cache_dir}")
    print(f"  Force: {args.force}")
    print()
    
    success_count = 0
    total_count = len(args.symbols) * len(args.timeframes)
    
    for symbol in args.symbols:
        for timeframe in args.timeframes:
            success = bootstrap_symbol(
                symbol,
                timeframe,
                start_date,
                end_date,
                output_dir,
                cache_dir,
                force=args.force
            )
            if success:
                success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Bootstrap complete: {success_count}/{total_count} successful")
    print(f"{'='*60}")


def cmd_update(args):
    """Execute update command"""
    output_dir = Path(args.out)
    
    print(f"Update Configuration:")
    print(f"  Symbols: {', '.join(args.symbols)}")
    print(f"  Timeframes: {', '.join(args.timeframes)}")
    print(f"  Output dir: {output_dir}")
    print()
    
    if not CCXT_AVAILABLE:
        print("Error: ccxt not installed. Install with: pip install ccxt")
        sys.exit(1)
    
    success_count = 0
    total_count = len(args.symbols) * len(args.timeframes)
    
    for symbol in args.symbols:
        for timeframe in args.timeframes:
            success = update_symbol(
                symbol,
                timeframe,
                output_dir,
                limit=args.limit
            )
            if success:
                success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Update complete: {success_count}/{total_count} successful")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description='Binance USDT-M Perpetual Futures OHLCV Data Downloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Bootstrap command
    bootstrap_parser = subparsers.add_parser(
        'bootstrap',
        help='Download bulk historical data from Binance Vision'
    )
    bootstrap_parser.add_argument(
        '--symbols',
        nargs='+',
        required=True,
        help='Symbols to download (e.g., BTCUSDT ETHUSDT)'
    )
    bootstrap_parser.add_argument(
        '--timeframes',
        nargs='+',
        required=True,
        help='Timeframes to download (e.g., 15m 1h 4h)'
    )
    bootstrap_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    bootstrap_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    bootstrap_parser.add_argument(
        '--out',
        default='./data/binance_futures',
        help='Output directory (default: ./data/binance_futures)'
    )
    bootstrap_parser.add_argument(
        '--cache',
        default='./data/.cache/binance_vision',
        help='Cache directory for zip files (default: ./data/.cache/binance_vision)'
    )
    bootstrap_parser.add_argument(
        '--force',
        action='store_true',
        help='Force redownload even if files exist'
    )
    
    # Update command
    update_parser = subparsers.add_parser(
        'update',
        help='Update existing data with latest candles via CCXT'
    )
    update_parser.add_argument(
        '--symbols',
        nargs='+',
        required=True,
        help='Symbols to update (e.g., BTCUSDT ETHUSDT)'
    )
    update_parser.add_argument(
        '--timeframes',
        nargs='+',
        required=True,
        help='Timeframes to update (e.g., 15m 1h 4h)'
    )
    update_parser.add_argument(
        '--out',
        default='./data/binance_futures',
        help='Output directory (default: ./data/binance_futures)'
    )
    update_parser.add_argument(
        '--limit',
        type=int,
        default=1000,
        help='Max candles to fetch per update (default: 1000)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'bootstrap':
        cmd_bootstrap(args)
    elif args.command == 'update':
        cmd_update(args)


if __name__ == '__main__':
    main()
