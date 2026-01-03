"""Tests for Multi-Timeframe Timestamp Mapping

These tests validate that LTF timestamps correctly map to HTF and ITF indices
using the bisect-based mapping functions.
"""

import pytest
from datetime import datetime, timezone, timedelta
from strategies.supply_demand_v1.runner import (
    find_htf_index_at_ltf_timestamp,
    find_itf_index_at_ltf_timestamp,
)


def test_htf_mapping_exact_match():
    """Test HTF mapping when LTF timestamp exactly matches HTF timestamp"""
    # Create HTF candles at 4-hour intervals
    htf_candles = [
        {'timestamp': datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp exactly matches HTF timestamp
    ltf_ts = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    
    assert htf_idx == 1  # Should point to the 4:00 HTF candle


def test_htf_mapping_between_candles():
    """Test HTF mapping when LTF timestamp falls between HTF candles"""
    # Create HTF candles at 4-hour intervals
    htf_candles = [
        {'timestamp': datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp falls between 4:00 and 8:00 HTF candles
    ltf_ts = datetime(2024, 1, 1, 6, 30, tzinfo=timezone.utc)
    
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    
    assert htf_idx == 1  # Should point to the most recent HTF candle (4:00)


def test_htf_mapping_before_first_candle():
    """Test HTF mapping when LTF timestamp is before first HTF candle"""
    # Create HTF candles starting at 4:00
    htf_candles = [
        {'timestamp': datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp is before first HTF candle
    ltf_ts = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)
    
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    
    assert htf_idx is None  # No valid HTF candle available


def test_htf_mapping_at_last_candle():
    """Test HTF mapping when LTF timestamp equals last HTF candle"""
    # Create HTF candles
    htf_candles = [
        {'timestamp': datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp equals last HTF candle
    ltf_ts = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
    
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    
    assert htf_idx == 2  # Should point to the last HTF candle


def test_htf_mapping_empty_list():
    """Test HTF mapping with empty candle list"""
    htf_candles = []
    ltf_ts = datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc)
    
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    
    assert htf_idx is None


def test_itf_mapping_exact_match():
    """Test ITF mapping when LTF timestamp exactly matches ITF timestamp"""
    # Create ITF candles at 1-hour intervals
    itf_candles = [
        {'timestamp': datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp exactly matches ITF timestamp
    ltf_ts = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
    
    itf_idx = find_itf_index_at_ltf_timestamp(ltf_ts, itf_candles)
    
    assert itf_idx == 1  # Should point to the 11:00 ITF candle


def test_itf_mapping_between_candles():
    """Test ITF mapping when LTF timestamp falls between ITF candles"""
    # Create ITF candles at 1-hour intervals
    itf_candles = [
        {'timestamp': datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc), 'close': 101},
        {'timestamp': datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc), 'close': 102},
    ]
    
    # LTF timestamp falls between 11:00 and 12:00 ITF candles
    ltf_ts = datetime(2024, 1, 1, 11, 30, tzinfo=timezone.utc)
    
    itf_idx = find_itf_index_at_ltf_timestamp(ltf_ts, itf_candles)
    
    assert itf_idx == 1  # Should point to the most recent ITF candle (11:00)


def test_itf_mapping_multiple_ltf_per_itf():
    """Test that multiple LTF candles map to the same ITF candle"""
    # Create ITF candles at 1-hour intervals
    itf_candles = [
        {'timestamp': datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), 'close': 100},
        {'timestamp': datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc), 'close': 101},
    ]
    
    # Multiple LTF timestamps within the same ITF period
    ltf_timestamps = [
        datetime(2024, 1, 1, 10, 15, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 10, 45, tzinfo=timezone.utc),
    ]
    
    for ltf_ts in ltf_timestamps:
        itf_idx = find_itf_index_at_ltf_timestamp(ltf_ts, itf_candles)
        assert itf_idx == 0  # All should map to the 10:00 ITF candle


def test_realistic_15m_1h_4h_alignment():
    """Test realistic 15m LTF with 1h ITF and 4h HTF alignment"""
    # Create realistic multi-timeframe candles
    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    
    # HTF: 4-hour candles
    htf_candles = [
        {'timestamp': base_time + timedelta(hours=4*i), 'close': 100+i}
        for i in range(6)  # 0:00, 4:00, 8:00, 12:00, 16:00, 20:00
    ]
    
    # ITF: 1-hour candles
    itf_candles = [
        {'timestamp': base_time + timedelta(hours=i), 'close': 100+i*0.1}
        for i in range(24)  # 0:00 to 23:00
    ]
    
    # LTF: 15-minute candles
    ltf_candles = [
        {'timestamp': base_time + timedelta(minutes=15*i), 'close': 100+i*0.01}
        for i in range(96)  # 0:00 to 23:45
    ]
    
    # Test specific LTF -> ITF mappings
    # 10:30 LTF should map to 10:00 ITF (index 10)
    ltf_ts = datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)
    itf_idx = find_itf_index_at_ltf_timestamp(ltf_ts, itf_candles)
    assert itf_idx == 10
    assert itf_candles[itf_idx]['timestamp'] == datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    
    # Test specific LTF -> HTF mappings
    # 10:30 LTF should map to 8:00 HTF (index 2)
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    assert htf_idx == 2
    assert htf_candles[htf_idx]['timestamp'] == datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
    
    # Test at HTF boundary (12:00)
    ltf_ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    htf_idx = find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles)
    assert htf_idx == 3
    assert htf_candles[htf_idx]['timestamp'] == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_edge_case_single_candle():
    """Test mapping with single candle in HTF/ITF"""
    htf_candles = [
        {'timestamp': datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc), 'close': 100}
    ]
    
    # Before the single candle
    ltf_ts = datetime(2023, 12, 31, 23, 0, tzinfo=timezone.utc)
    assert find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles) is None
    
    # At the single candle
    ltf_ts = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles) == 0
    
    # After the single candle
    ltf_ts = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)
    assert find_htf_index_at_ltf_timestamp(ltf_ts, htf_candles) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
