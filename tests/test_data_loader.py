"""Tests for historical data loader

Tests cover:
- Loading historical candles from CSV
- Validation of candle data integrity
- Timestamp monotonicity
- Checksum generation
- Error handling for missing/invalid data
"""

import pytest
import tempfile
import csv
from pathlib import Path
from datetime import datetime, timezone, timedelta

from strategies.supply_demand_v1.data_loader import (
    load_historical_candles,
    validate_candles,
    generate_sample_historical_data,
    HistoricalDataError,
    parse_timestamp,
)

from strategies.supply_demand_v1.runner import calculate_candle_checksum


class TestParseTimestamp:
    """Test timestamp parsing"""
    
    def test_parse_iso_format(self):
        """Test parsing ISO format timestamp"""
        ts_str = "2024-01-01T00:00:00+00:00"
        dt = parse_timestamp(ts_str)
        
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.tzinfo == timezone.utc
    
    def test_parse_iso_format_with_z(self):
        """Test parsing ISO format with Z suffix"""
        ts_str = "2024-01-01T12:30:00Z"
        dt = parse_timestamp(ts_str)
        
        assert dt.hour == 12
        assert dt.minute == 30
        assert dt.tzinfo == timezone.utc
    
    def test_parse_space_separated(self):
        """Test parsing space-separated format"""
        ts_str = "2024-01-01 15:45:30"
        dt = parse_timestamp(ts_str)
        
        assert dt.hour == 15
        assert dt.minute == 45
        assert dt.second == 30
        assert dt.tzinfo == timezone.utc
    
    def test_parse_unix_timestamp(self):
        """Test parsing Unix timestamp (milliseconds)"""
        ts_str = "1704067200000"  # 2024-01-01 00:00:00 UTC
        dt = parse_timestamp(ts_str)
        
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.tzinfo == timezone.utc


class TestValidateCandles:
    """Test candle validation"""
    
    def test_validate_valid_candles(self):
        """Test validation passes for valid candles"""
        candles = [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000.0,
            }
            for i in range(150)
        ]
        
        # Update timestamps to be monotonic
        for i, candle in enumerate(candles):
            candle['timestamp'] = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15*i)
        
        # Should not raise
        validate_candles(candles, 'TEST/USDT', min_candles=100)
    
    def test_validate_empty_candles(self):
        """Test validation fails for empty candles"""
        with pytest.raises(HistoricalDataError, match="No candles loaded"):
            validate_candles([], 'TEST/USDT')
    
    def test_validate_insufficient_candles(self):
        """Test validation fails when candle count below minimum"""
        candles = [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15*i),
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000.0,
            }
            for i in range(50)
        ]
        
        with pytest.raises(HistoricalDataError, match="Insufficient candles.*got 50.*minimum required is 100"):
            validate_candles(candles, 'TEST/USDT', min_candles=100)
    
    def test_validate_missing_fields(self):
        """Test validation fails when required fields missing"""
        candles = [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                # Missing 'close' and 'volume'
            }
        ]
        
        with pytest.raises(HistoricalDataError, match="missing required field"):
            validate_candles(candles, 'TEST/USDT', min_candles=1)
    
    def test_validate_non_monotonic_timestamps(self):
        """Test validation fails for non-monotonic timestamps"""
        candles = [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000.0,
            },
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),  # Same timestamp!
                'open': 102.0,
                'high': 108.0,
                'low': 100.0,
                'close': 106.0,
                'volume': 1200.0,
            }
        ]
        
        with pytest.raises(HistoricalDataError, match="Non-monotonic timestamps"):
            validate_candles(candles, 'TEST/USDT', min_candles=1)
    
    def test_validate_negative_prices(self):
        """Test validation fails for negative prices"""
        candles = [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'open': -100.0,  # Negative price!
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000.0,
            }
        ] + [
            {
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15*i),
                'open': 100.0,
                'high': 105.0,
                'low': 95.0,
                'close': 102.0,
                'volume': 1000.0,
            }
            for i in range(1, 150)
        ]
        
        with pytest.raises(HistoricalDataError, match="Invalid price values"):
            validate_candles(candles, 'TEST/USDT', min_candles=100)


class TestLoadHistoricalCandles:
    """Test loading historical candles from CSV"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_load_valid_csv(self, temp_data_dir):
        """Test loading valid CSV file"""
        # Create directory structure
        subdir = temp_data_dir / "binance_futures"
        subdir.mkdir(parents=True)
        
        # Create CSV file
        csv_file = subdir / "BTCUSDT_15m.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            for i in range(200):
                ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15*i)
                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    42000.0 + i * 10,
                    42500.0 + i * 10,
                    41500.0 + i * 10,
                    42300.0 + i * 10,
                    1234.56
                ])
        
        # Load candles
        candles = load_historical_candles(
            symbol='BTCUSDT',
            timeframe='15m',
            start_date='2024-01-01',
            end_date='2024-01-31',
            data_dir=temp_data_dir,
            exchange='binance',
            market_type='futures'
        )
        
        # Assertions
        assert len(candles) > 0
        assert all('open' in c for c in candles)
        assert all('high' in c for c in candles)
        assert all('low' in c for c in candles)
        assert all('close' in c for c in candles)
        assert all('volume' in c for c in candles)
        assert all('timestamp' in c for c in candles)
        assert all('symbol' in c for c in candles)
        assert all(c['symbol'] == 'BTCUSDT' for c in candles)
        
        # Check timestamps are monotonic
        for i in range(1, len(candles)):
            assert candles[i]['timestamp'] > candles[i-1]['timestamp']
        
        # Check checksum is non-null
        checksum = calculate_candle_checksum(candles)
        assert checksum is not None
        assert len(checksum) == 32  # MD5 hash length
    
    def test_load_missing_file(self, temp_data_dir):
        """Test error when CSV file doesn't exist"""
        with pytest.raises(HistoricalDataError, match="Historical data file not found"):
            load_historical_candles(
                symbol='BTCUSDT',
                timeframe='15m',
                start_date='2024-01-01',
                end_date='2024-01-31',
                data_dir=temp_data_dir,
                exchange='binance',
                market_type='futures'
            )
    
    def test_load_csv_missing_columns(self, temp_data_dir):
        """Test error when CSV missing required columns"""
        # Create directory structure
        subdir = temp_data_dir / "binance_futures"
        subdir.mkdir(parents=True)
        
        # Create CSV file with missing columns
        csv_file = subdir / "BTCUSDT_15m.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high'])  # Missing low, close, volume
            writer.writerow(['2024-01-01 00:00:00', '42000', '42500'])
        
        with pytest.raises(HistoricalDataError, match="missing required columns"):
            load_historical_candles(
                symbol='BTCUSDT',
                timeframe='15m',
                start_date='2024-01-01',
                end_date='2024-01-31',
                data_dir=temp_data_dir,
                exchange='binance',
                market_type='futures'
            )
    
    def test_load_csv_date_filtering(self, temp_data_dir):
        """Test that candles are filtered by date range"""
        # Create directory structure
        subdir = temp_data_dir / "binance_futures"
        subdir.mkdir(parents=True)
        
        # Create CSV file with wider date range
        csv_file = subdir / "BTCUSDT_15m.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Write data for 6 months (Jan to Jun)
            for month in range(1, 7):
                for day in range(1, 28):  # Simplified - 27 days per month
                    for hour in range(0, 24, 4):  # Every 4 hours
                        ts = datetime(2024, month, day, hour, tzinfo=timezone.utc)
                        writer.writerow([
                            ts.strftime('%Y-%m-%d %H:%M:%S'),
                            42000.0,
                            42500.0,
                            41500.0,
                            42300.0,
                            1234.56
                        ])
        
        # Load candles for only Jan-Feb
        candles = load_historical_candles(
            symbol='BTCUSDT',
            timeframe='15m',
            start_date='2024-01-01',
            end_date='2024-02-29',
            data_dir=temp_data_dir,
            exchange='binance',
            market_type='futures'
        )
        
        # All candles should be within Jan-Feb
        assert all(candles[0]['timestamp'] >= datetime(2024, 1, 1, tzinfo=timezone.utc) for _ in [1])
        assert all(candles[-1]['timestamp'] <= datetime(2024, 2, 29, tzinfo=timezone.utc) for _ in [1])


class TestGenerateSampleHistoricalData:
    """Test sample data generation"""
    
    def test_generate_sample_data(self):
        """Test sample data generation creates valid files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            symbols = ['BTCUSDT', 'ETHUSDT']
            
            generate_sample_historical_data(
                output_dir,
                symbols,
                timeframe='15m',
                num_candles=200,
                exchange='binance',
                market_type='futures'
            )
            
            # Check files were created
            for symbol in symbols:
                csv_file = output_dir / 'binance_futures' / f'{symbol}_15m.csv'
                assert csv_file.exists()
                
                # Check file has header and data
                with open(csv_file, 'r') as f:
                    lines = f.readlines()
                    assert len(lines) == 201  # Header + 200 data rows
                    assert 'timestamp,open,high,low,close,volume' in lines[0]
    
    def test_generated_data_can_be_loaded(self):
        """Test that generated sample data can be loaded back"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            symbols = ['BTCUSDT']
            
            # Generate sample data
            generate_sample_historical_data(
                output_dir,
                symbols,
                timeframe='15m',
                num_candles=500,
                exchange='binance',
                market_type='futures'
            )
            
            # Try to load it back
            candles = load_historical_candles(
                symbol='BTCUSDT',
                timeframe='15m',
                start_date='2024-01-01',
                end_date='2024-01-31',
                data_dir=output_dir,
                exchange='binance',
                market_type='futures'
            )
            
            # Should load successfully
            assert len(candles) > 0
            
            # Validate it passes all checks
            validate_candles(candles, 'BTCUSDT', min_candles=100)
