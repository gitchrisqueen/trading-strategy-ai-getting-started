"""Unit tests for OHLCV validation tool"""
import csv
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from data_tools.validate_ohlcv import (
    extract_timeframe_from_filename,
    validate_csv_file,
    TIMEFRAME_INTERVALS
)


class TestTimeframeExtraction:
    """Test timeframe extraction from filenames"""
    
    def test_extract_15m_timeframe(self):
        """Should extract 15m from BTCUSDT_15m.csv"""
        path = Path("BTCUSDT_15m.csv")
        assert extract_timeframe_from_filename(path) == "15m"
    
    def test_extract_1h_timeframe(self):
        """Should extract 1h from ETHUSDT_1h.csv"""
        path = Path("ETHUSDT_1h.csv")
        assert extract_timeframe_from_filename(path) == "1h"
    
    def test_extract_4h_timeframe(self):
        """Should extract 4h from BNBUSDT_4h.csv"""
        path = Path("BNBUSDT_4h.csv")
        assert extract_timeframe_from_filename(path) == "4h"
    
    def test_extract_1d_timeframe(self):
        """Should extract 1d from SOLUSDT_1d.csv"""
        path = Path("SOLUSDT_1d.csv")
        assert extract_timeframe_from_filename(path) == "1d"
    
    def test_no_timeframe_in_filename(self):
        """Should return None if no valid timeframe found"""
        path = Path("data.csv")
        assert extract_timeframe_from_filename(path) is None
    
    def test_invalid_timeframe(self):
        """Should return None for invalid timeframe"""
        path = Path("BTCUSDT_999m.csv")
        assert extract_timeframe_from_filename(path) is None


class TestValidationWithCorrectSpacing:
    """Test validation with correct interval spacing"""
    
    def create_test_csv(self, timeframe: str, num_rows: int = 10):
        """Helper to create a test CSV file with correct spacing"""
        interval = TIMEFRAME_INTERVALS[timeframe]
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix=f'_{timeframe}.csv',
            delete=False,
            newline=''
        ) as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            ts = datetime(2024, 1, 1, 0, 0, 0)
            for i in range(num_rows):
                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    100.0 + i,
                    101.0 + i,
                    99.0 + i,
                    100.5 + i,
                    1000.0
                ])
                ts += interval
            
            return Path(f.name)
    
    def test_15m_file_validates_correctly(self):
        """15m file with correct spacing should pass"""
        csv_path = self.create_test_csv('15m')
        try:
            result = validate_csv_file(csv_path)
            assert result.is_valid(), f"Should pass validation, errors: {result.errors}"
            assert result.timeframe == '15m'
            assert result.total_rows == 10
        finally:
            csv_path.unlink()
    
    def test_1h_file_validates_correctly(self):
        """1h file with correct spacing should pass"""
        csv_path = self.create_test_csv('1h')
        try:
            result = validate_csv_file(csv_path)
            assert result.is_valid(), f"Should pass validation, errors: {result.errors}"
            assert result.timeframe == '1h'
            assert result.total_rows == 10
        finally:
            csv_path.unlink()
    
    def test_4h_file_validates_correctly(self):
        """4h file with correct spacing should pass"""
        csv_path = self.create_test_csv('4h')
        try:
            result = validate_csv_file(csv_path)
            assert result.is_valid(), f"Should pass validation, errors: {result.errors}"
            assert result.timeframe == '4h'
            assert result.total_rows == 10
        finally:
            csv_path.unlink()
    
    def test_1h_file_does_not_use_15m_interval(self):
        """1h file should not be validated with 15m interval"""
        csv_path = self.create_test_csv('1h')
        try:
            result = validate_csv_file(csv_path)
            # Should pass because it infers 1h from filename
            assert result.is_valid()
            assert result.timeframe == '1h'
            
            # Should NOT have gap errors (which would occur if using 15m interval)
            gap_errors = [e for e in result.errors if e.error_type == 'GAP_DETECTED']
            assert len(gap_errors) == 0, "Should not detect gaps when using correct interval"
        finally:
            csv_path.unlink()


class TestGapDetection:
    """Test gap detection in different timeframes"""
    
    def create_csv_with_gap(self, timeframe: str, gap_intervals: int = 2):
        """Create CSV with intentional gap"""
        interval = TIMEFRAME_INTERVALS[timeframe]
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix=f'_{timeframe}.csv',
            delete=False,
            newline=''
        ) as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            ts = datetime(2024, 1, 1, 0, 0, 0)
            
            # Write first 5 rows
            for i in range(5):
                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    100.0 + i,
                    101.0 + i,
                    99.0 + i,
                    100.5 + i,
                    1000.0
                ])
                ts += interval
            
            # Skip intervals to create gap
            ts += interval * gap_intervals
            
            # Write next 5 rows
            for i in range(5, 10):
                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    100.0 + i,
                    101.0 + i,
                    99.0 + i,
                    100.5 + i,
                    1000.0
                ])
                ts += interval
            
            return Path(f.name)
    
    def test_gap_is_detected(self):
        """Gap should be detected in 1h file"""
        csv_path = self.create_csv_with_gap('1h', gap_intervals=2)
        try:
            result = validate_csv_file(csv_path, max_gap_intervals=0)
            assert not result.is_valid(), "Should fail validation due to gap"
            
            gap_errors = [e for e in result.errors if e.error_type == 'GAP_DETECTED']
            assert len(gap_errors) == 1, "Should detect exactly one gap"
            assert gap_errors[0].details['missing_intervals'] == 2
        finally:
            csv_path.unlink()
    
    def test_gap_tolerance(self):
        """Gap should pass with appropriate tolerance"""
        csv_path = self.create_csv_with_gap('1h', gap_intervals=2)
        try:
            # With tolerance of 2, should pass
            result = validate_csv_file(csv_path, max_gap_intervals=2)
            assert result.is_valid(), "Should pass with tolerance"
        finally:
            csv_path.unlink()
    
    def test_gap_in_4h_file(self):
        """Gap detection should work correctly for 4h files"""
        csv_path = self.create_csv_with_gap('4h', gap_intervals=1)
        try:
            result = validate_csv_file(csv_path, max_gap_intervals=0)
            assert not result.is_valid(), "Should fail validation due to gap"
            
            gap_errors = [e for e in result.errors if e.error_type == 'GAP_DETECTED']
            assert len(gap_errors) == 1
            assert gap_errors[0].details['missing_intervals'] == 1
        finally:
            csv_path.unlink()


class TestExplicitTimeframe:
    """Test validation with explicitly provided timeframe"""
    
    def test_explicit_timeframe_overrides_filename(self):
        """Explicitly provided timeframe should be used"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='_15m.csv',
            delete=False,
            newline=''
        ) as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Write with 1h spacing
            ts = datetime(2024, 1, 1, 0, 0, 0)
            for i in range(5):
                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1000.0
                ])
                ts += timedelta(hours=1)
            
            csv_path = Path(f.name)
        
        try:
            # Validate with explicit 1h timeframe (should pass)
            result = validate_csv_file(csv_path, timeframe='1h')
            assert result.is_valid()
            assert result.timeframe == '1h'
        finally:
            csv_path.unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
