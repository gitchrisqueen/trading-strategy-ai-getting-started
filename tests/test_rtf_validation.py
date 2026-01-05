"""Unit tests for RTF timeframe validation

Tests that RTF (Refining TimeFrame) must be lower than LTF (Lower TimeFrame).
"""

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from strategies.supply_demand_v1.csv_backtest_adapter import validate_timeframe_hierarchy


class TestRTFValidation:
    """Test RTF timeframe validation"""
    
    def test_rtf_none_is_valid(self):
        """Test that RTF=None is valid (RTF is optional)"""
        # Should not raise
        validate_timeframe_hierarchy('15m', None)
        print("✓ RTF=None is valid")
    
    def test_rtf_lower_than_ltf_is_valid(self):
        """Test that RTF < LTF is valid"""
        # Valid combinations
        validate_timeframe_hierarchy('15m', '5m')   # 5m < 15m ✓
        validate_timeframe_hierarchy('15m', '1m')   # 1m < 15m ✓
        validate_timeframe_hierarchy('1h', '15m')   # 15m < 1h ✓
        validate_timeframe_hierarchy('1h', '5m')    # 5m < 1h ✓
        validate_timeframe_hierarchy('4h', '1h')    # 1h < 4h ✓
        print("✓ RTF < LTF combinations are valid")
    
    def test_rtf_equal_to_ltf_raises_error(self):
        """Test that RTF == LTF raises ValueError"""
        try:
            validate_timeframe_hierarchy('15m', '15m')  # Equal - should fail
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "must be LOWER than" in str(e)
            print(f"✓ RTF == LTF raises error: {e}")
    
    def test_rtf_higher_than_ltf_raises_error(self):
        """Test that RTF > LTF raises ValueError"""
        try:
            validate_timeframe_hierarchy('15m', '1h')  # 1h > 15m - should fail
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "must be LOWER than" in str(e)
            print(f"✓ RTF > LTF raises error: {e}")
    
    def test_invalid_ltf_raises_error(self):
        """Test that invalid LTF raises ValueError"""
        try:
            validate_timeframe_hierarchy('invalid', '5m')
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid LTF timeframe" in str(e)
            print(f"✓ Invalid LTF raises error: {e}")
    
    def test_invalid_rtf_raises_error(self):
        """Test that invalid RTF raises ValueError"""
        try:
            validate_timeframe_hierarchy('15m', 'invalid')
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid RTF timeframe" in str(e)
            print(f"✓ Invalid RTF raises error: {e}")
    
    def test_error_message_includes_valid_options(self):
        """Test that error message includes valid RTF options"""
        try:
            validate_timeframe_hierarchy('15m', '1h')
            assert False, "Should have raised ValueError"
        except ValueError as e:
            error_msg = str(e)
            # Should suggest valid RTF options for LTF=15m (1m, 5m)
            assert "1m" in error_msg or "5m" in error_msg
            assert "Valid RTF options" in error_msg
            print(f"✓ Error message includes valid options:\n  {error_msg}")


def test_all_combinations():
    """Test various RTF/LTF combinations"""
    
    print("\n" + "="*80)
    print("TESTING RTF TIMEFRAME VALIDATION")
    print("="*80)
    
    test = TestRTFValidation()
    
    test.test_rtf_none_is_valid()
    test.test_rtf_lower_than_ltf_is_valid()
    test.test_rtf_equal_to_ltf_raises_error()
    test.test_rtf_higher_than_ltf_raises_error()
    test.test_invalid_ltf_raises_error()
    test.test_invalid_rtf_raises_error()
    test.test_error_message_includes_valid_options()
    
    print("\n" + "="*80)
    print("✅ ALL RTF VALIDATION TESTS PASSED")
    print("="*80)


if __name__ == "__main__":
    test_all_combinations()
