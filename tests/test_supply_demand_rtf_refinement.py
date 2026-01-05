"""Tests for RTF Entry Refinement Stage

Tests the RTF (Refining Timeframe) entry refinement functions that filter
order placement after proximity trigger passes.
"""

import pytest
from strategies.supply_demand_v1.strategy_core import (
    check_bullish_engulfing,
    check_bearish_engulfing,
    check_bullish_rejection,
    check_bearish_rejection,
    check_bullish_micro_break,
    check_bearish_micro_break,
    check_rtf_refinement,
    SupplyDemandParameters,
    Zone,
    ZoneType,
)


# ============================================================================
# Test Bullish Engulfing
# ============================================================================


def test_check_bullish_engulfing_pass():
    """Test bullish engulfing pattern detection - should pass"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},   # Previous bearish
        {'open': 98, 'high': 103, 'low': 97, 'close': 102},   # Current bullish, engulfs previous
    ]
    
    assert check_bullish_engulfing(candles, 1, lookback=2) is True


def test_check_bullish_engulfing_fail_not_engulfing():
    """Test bullish engulfing - fails because current doesn't engulf previous"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},   # Previous bearish
        {'open': 99, 'high': 101, 'low': 98, 'close': 100},   # Current bullish but doesn't engulf
    ]
    
    assert check_bullish_engulfing(candles, 1, lookback=2) is False


def test_check_bullish_engulfing_fail_previous_not_bearish():
    """Test bullish engulfing - fails because previous is not bearish"""
    candles = [
        {'open': 99, 'high': 102, 'low': 98, 'close': 101},   # Previous bullish
        {'open': 98, 'high': 103, 'low': 97, 'close': 102},   # Current bullish
    ]
    
    assert check_bullish_engulfing(candles, 1, lookback=2) is False


def test_check_bullish_engulfing_insufficient_candles():
    """Test bullish engulfing - fails with insufficient candles"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},
    ]
    
    assert check_bullish_engulfing(candles, 0, lookback=2) is False


# ============================================================================
# Test Bearish Engulfing
# ============================================================================


def test_check_bearish_engulfing_pass():
    """Test bearish engulfing pattern detection - should pass"""
    candles = [
        {'open': 99, 'high': 102, 'low': 98, 'close': 101},   # Previous bullish
        {'open': 102, 'high': 103, 'low': 97, 'close': 98},   # Current bearish, engulfs previous
    ]
    
    assert check_bearish_engulfing(candles, 1, lookback=2) is True


def test_check_bearish_engulfing_fail_not_engulfing():
    """Test bearish engulfing - fails because current doesn't engulf previous"""
    candles = [
        {'open': 99, 'high': 102, 'low': 98, 'close': 101},   # Previous bullish
        {'open': 101, 'high': 102, 'low': 99, 'close': 100},  # Current bearish but doesn't engulf
    ]
    
    assert check_bearish_engulfing(candles, 1, lookback=2) is False


# ============================================================================
# Test Bullish Rejection
# ============================================================================


def test_check_bullish_rejection_pass():
    """Test bullish rejection wick - should pass"""
    candles = [
        # Candle with long lower wick inside zone, closes in upper half
        {'open': 100, 'high': 102, 'low': 95, 'close': 101},
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    assert check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2) is True


def test_check_bullish_rejection_fail_no_wick():
    """Test bullish rejection - fails with no significant lower wick"""
    candles = [
        # Candle closes near low (no rejection)
        {'open': 100, 'high': 102, 'low': 95, 'close': 96},
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    assert check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2) is False


def test_check_bullish_rejection_fail_didnt_touch_zone():
    """Test bullish rejection - fails because candle didn't reach zone"""
    candles = [
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    assert check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2) is False


# ============================================================================
# Test Bearish Rejection
# ============================================================================


def test_check_bearish_rejection_pass():
    """Test bearish rejection wick - should pass"""
    candles = [
        # Candle with long upper wick inside zone, closes in lower half
        {'open': 100, 'high': 105, 'low': 98, 'close': 99},
    ]
    
    zone_bottom = 102
    zone_top = 105
    
    assert check_bearish_rejection(candles, 0, zone_bottom, zone_top, lookback=2) is True


def test_check_bearish_rejection_fail_no_wick():
    """Test bearish rejection - fails with no significant upper wick"""
    candles = [
        # Candle closes near high (no rejection)
        {'open': 100, 'high': 105, 'low': 98, 'close': 104},
    ]
    
    zone_bottom = 102
    zone_top = 105
    
    assert check_bearish_rejection(candles, 0, zone_bottom, zone_top, lookback=2) is False


# ============================================================================
# Test Bullish Micro Break
# ============================================================================


def test_check_bullish_micro_break_pass():
    """Test bullish micro structure break - should pass"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 101},   # Previous high = 102
        {'open': 101, 'high': 104, 'low': 100, 'close': 103},  # Current close > previous high
    ]
    
    assert check_bullish_micro_break(candles, 1, lookback=2) is True


def test_check_bullish_micro_break_fail():
    """Test bullish micro structure break - fails"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 101},   # Previous high = 102
        {'open': 101, 'high': 102, 'low': 100, 'close': 101},  # Current close <= previous high
    ]
    
    assert check_bullish_micro_break(candles, 1, lookback=2) is False


# ============================================================================
# Test Bearish Micro Break
# ============================================================================


def test_check_bearish_micro_break_pass():
    """Test bearish micro structure break - should pass"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},    # Previous low = 98
        {'open': 99, 'high': 100, 'low': 96, 'close': 97},     # Current close < previous low
    ]
    
    assert check_bearish_micro_break(candles, 1, lookback=2) is True


def test_check_bearish_micro_break_fail():
    """Test bearish micro structure break - fails"""
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},    # Previous low = 98
        {'open': 99, 'high': 100, 'low': 98, 'close': 99},     # Current close >= previous low
    ]
    
    assert check_bearish_micro_break(candles, 1, lookback=2) is False


# ============================================================================
# Test check_rtf_refinement (Main Function)
# ============================================================================


def test_check_rtf_refinement_disabled():
    """Test RTF refinement - should always pass when disabled"""
    params = SupplyDemandParameters(rtf_refinement_enabled=False)
    
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},
        {'open': 99, 'high': 101, 'low': 98, 'close': 100},
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=102.0,
        distal=98.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should always pass when disabled
    assert check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params) is True


def test_check_rtf_refinement_engulfing_long():
    """Test RTF refinement with engulfing rule for LONG setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="engulfing",
        rtf_refinement_lookback=2
    )
    
    # Bullish engulfing pattern
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},   # Bearish
        {'open': 98, 'high': 103, 'low': 97, 'close': 102},   # Bullish engulfing
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=102.0,
        distal=98.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should pass with bullish engulfing for LONG (DEMAND polarity)
    assert check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params) is True


def test_check_rtf_refinement_engulfing_short():
    """Test RTF refinement with engulfing rule for SHORT setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="engulfing",
        rtf_refinement_lookback=2
    )
    
    # Bearish engulfing pattern
    candles = [
        {'open': 99, 'high': 102, 'low': 98, 'close': 101},   # Bullish
        {'open': 102, 'high': 103, 'low': 97, 'close': 98},   # Bearish engulfing
    ]
    
    zone = Zone(
        zone_type=ZoneType.SUPPLY,
        proximal=98.0,
        distal=102.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should pass with bearish engulfing for SHORT (SUPPLY polarity)
    assert check_rtf_refinement(candles, 1, zone, ZoneType.SUPPLY, params) is True


def test_check_rtf_refinement_micro_break_long():
    """Test RTF refinement with micro_break rule for LONG setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="micro_break",
        rtf_refinement_lookback=2
    )
    
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 101},   # Previous high = 102
        {'open': 101, 'high': 104, 'low': 100, 'close': 103},  # Close > previous high
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=102.0,
        distal=98.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should pass with bullish micro break for LONG
    assert check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params) is True


def test_check_rtf_refinement_insufficient_candles():
    """Test RTF refinement - should fail with insufficient candles"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="engulfing",
        rtf_refinement_lookback=2
    )
    
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=102.0,
        distal=98.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should fail with insufficient candles
    assert check_rtf_refinement(candles, 0, zone, ZoneType.DEMAND, params) is False


def test_check_rtf_refinement_unknown_rule():
    """Test RTF refinement - should fail with unknown rule"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="unknown_rule",
        rtf_refinement_lookback=2
    )
    
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},
        {'open': 99, 'high': 101, 'low': 98, 'close': 100},
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=102.0,
        distal=98.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should fail with unknown rule
    assert check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params) is False
