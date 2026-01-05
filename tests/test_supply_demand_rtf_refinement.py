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
    
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2)
    assert passed is True
    assert debug_info is None


def test_check_bullish_rejection_fail_no_wick():
    """Test bullish rejection - fails with no significant lower wick"""
    candles = [
        # Candle closes near low (no rejection)
        {'open': 100, 'high': 102, 'low': 95, 'close': 96},
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2)
    assert passed is False
    assert debug_info is not None
    assert "reason" in debug_info


def test_check_bullish_rejection_fail_didnt_touch_zone():
    """Test bullish rejection - fails because candle didn't reach zone"""
    candles = [
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2)
    assert passed is False
    assert debug_info is not None
    assert debug_info["reason"] == "didnt_touch_zone"


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
    
    passed, debug_info = check_bearish_rejection(candles, 0, zone_bottom, zone_top, lookback=2)
    assert passed is True
    assert debug_info is None


def test_check_bearish_rejection_fail_no_wick():
    """Test bearish rejection - fails with no significant upper wick"""
    candles = [
        # Candle closes near high (no rejection)
        {'open': 100, 'high': 105, 'low': 98, 'close': 104},
    ]
    
    zone_bottom = 102
    zone_top = 105
    
    passed, debug_info = check_bearish_rejection(candles, 0, zone_bottom, zone_top, lookback=2)
    assert passed is False
    assert debug_info is not None
    assert "reason" in debug_info


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
    
    # Should always pass when disabled (returns True, None, None)
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params)
    assert passed is True
    assert failure_reason is None
    assert debug_info is None


def test_check_rtf_refinement_engulfing_long():
    """Test RTF refinement with engulfing rule for LONG setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="engulfing",
        rtf_refinement_lookback=1  # Only need 1 previous candle for engulfing
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
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params)
    assert passed is True
    assert failure_reason is None
    assert debug_info is None


def test_check_rtf_refinement_engulfing_short():
    """Test RTF refinement with engulfing rule for SHORT setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="engulfing",
        rtf_refinement_lookback=1  # Only need 1 previous candle for engulfing
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
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.SUPPLY, params)
    assert passed is True
    assert failure_reason is None
    assert debug_info is None


def test_check_rtf_refinement_micro_break_long():
    """Test RTF refinement with micro_break rule for LONG setup"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="micro_break",
        rtf_refinement_lookback=1  # Only need 1 previous candle for micro_break
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
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params)
    assert passed is True
    assert failure_reason is None
    assert debug_info is None


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
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 0, zone, ZoneType.DEMAND, params)
    assert passed is False
    assert failure_reason == "insufficient_candles"
    assert debug_info is not None


def test_check_rtf_refinement_unknown_rule():
    """Test RTF refinement - should fail with unknown rule"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="unknown_rule",
        rtf_refinement_lookback=1  # Use lookback=1 to avoid insufficient_candles error
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
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params)
    assert passed is False
    assert failure_reason == "rejection_rule"
    assert debug_info is not None


# ============================================================================
# Test Configurable Rejection Parameters
# ============================================================================


def test_check_bullish_rejection_with_relaxed_wick_ratio():
    """Test bullish rejection with relaxed wick ratio threshold"""
    # Create candle with 35% wick ratio
    # open=100, low=90, close=107
    # range = 110 - 90 = 20
    # lower_wick = min(100, 107) - 90 = 10
    # WRONG - this gives 50% wick!
    # We need: lower_wick = 7 for 35% ratio
    # So: min(open, close) - low = 7  =>  min(open, close) = 97
    # We want close=107, so open must be 97 or less
    
    candles = [
        # Candle with 35% wick ratio: range=20, wick=7 (97-90), ratio=0.35
        {'open': 97, 'high': 110, 'low': 90, 'close': 107},
    ]
    
    zone_bottom = 90
    zone_top = 95
    
    # Should fail with default min_wick_ratio=0.40
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2, min_wick_ratio=0.40)
    assert passed is False
    assert debug_info["reason"] == "wick_too_small"
    assert 0.34 < debug_info["wick_ratio"] < 0.36  # Should be ~0.35
    
    # Should pass with relaxed min_wick_ratio=0.30
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2, min_wick_ratio=0.30)
    assert passed is True
    assert debug_info is None


def test_check_bullish_rejection_with_strict_body_ratio():
    """Test bullish rejection with strict body ratio threshold"""
    # We need a candle where:
    # - body_ratio > 0.50 (large body)
    # - wick_ratio >= 0.40 (sufficient wick to pass that check)
    # - close_position >= 0.5 (close in upper half)
    # Example: open=95, low=90, close=108, high=110
    # range = 20, body = 13, body_ratio = 0.65
    # lower_wick = 95 - 90 = 5, wick_ratio = 0.25 - FAILS wick check
    
    # Let me design correctly:
    # We want body_ratio = 0.55 and wick_ratio = 0.40
    # range = 20, so body = 11, wick = 8
    # If low = 90, then min(open, close) = 90 + 8 = 98
    # close must be > 100 (mid-range) for close_position
    # So close = 107, open = 98 (this gives body = 9, not 11)
    # Try: close = 109, open = 98 -> body = 11, wick = 8
    
    candles_large_body = [
        # range=20 (90 to 110), body=11 (98 to 109), lower_wick=8 (90 to 98)
        # body_ratio = 11/20 = 0.55, wick_ratio = 8/20 = 0.40
        {'open': 98, 'high': 110, 'low': 90, 'close': 109},
    ]
    
    zone_bottom = 90
    zone_top = 95
    
    # Should fail with default max_body_ratio=0.50 (body_ratio=0.55 > 0.50)
    passed, debug_info = check_bullish_rejection(candles_large_body, 0, zone_bottom, zone_top, lookback=2, max_body_ratio=0.50)
    assert passed is False
    assert debug_info["reason"] == "body_too_large"
    assert 0.54 < debug_info["body_ratio"] < 0.56  # Should be ~0.55
    
    # Should pass with relaxed max_body_ratio=0.60
    passed, debug_info = check_bullish_rejection(candles_large_body, 0, zone_bottom, zone_top, lookback=2, max_body_ratio=0.60)
    assert passed is True
    assert debug_info is None


def test_check_bullish_rejection_without_touch_zone_requirement():
    """Test bullish rejection without requiring zone touch"""
    candles = [
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},  # Doesn't touch zone
    ]
    
    zone_bottom = 95
    zone_top = 98
    
    # Should fail with require_touch_zone=True (default)
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2, require_touch_zone=True)
    assert passed is False
    assert debug_info["reason"] == "didnt_touch_zone"
    
    # Should allow evaluation without touch requirement
    # (will still fail other checks, but not due to touch)
    passed, debug_info = check_bullish_rejection(candles, 0, zone_bottom, zone_top, lookback=2, require_touch_zone=False)
    # May pass or fail based on other criteria, but won't be "didnt_touch_zone"
    if not passed:
        assert debug_info["reason"] != "didnt_touch_zone"


def test_check_rtf_refinement_rejection_with_custom_params():
    """Test RTF refinement with rejection rule using custom rejection params"""
    params = SupplyDemandParameters(
        rtf_refinement_enabled=True,
        rtf_refinement_rule="rejection",
        rtf_refinement_lookback=1,  # Only need 1 candle for lookback
        # Relaxed parameters
        rejection_min_wick_ratio=0.30,  # Lower than default 0.40
        rejection_max_body_ratio=0.60,  # Higher than default 0.50
        rejection_require_close_in_direction=True,
        rejection_require_touch_zone=True,
    )
    
    # Candle with 35% wick ratio (passes relaxed 0.30, would fail default 0.40)
    # range=20 (90 to 110), lower_wick=7 (90 to 97), wick_ratio=0.35
    # close=107 -> close_position = (107-90)/20 = 0.85 (passes)
    # body=10 (97 to 107), body_ratio=0.50 (passes 0.60)
    candles = [
        {'open': 100, 'high': 102, 'low': 98, 'close': 99},  # Previous candle (needed for lookback)
        {'open': 97, 'high': 110, 'low': 90, 'close': 107},  # Test candle
    ]
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=95.0,
        distal=90.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=0,
        legout_end_idx=0,
        base_len=1,
        legout_len=1,
    )
    
    # Should pass with relaxed parameters (test candle is at index 1)
    passed, failure_reason, debug_info = check_rtf_refinement(candles, 1, zone, ZoneType.DEMAND, params)
    assert passed is True
    assert failure_reason is None
    assert debug_info is None
