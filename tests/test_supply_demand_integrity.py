"""Unit tests for supply and demand strategy backtest integrity validation

Tests cover:
- Look-ahead detection (zone used before creation)
- Entry timing validation (entry after zone creation)
- R calculation consistency
- Minimum R enforcement
"""

import pytest
from datetime import datetime, timedelta
from strategies.supply_demand_v1.integrity import (
    validate_no_lookahead,
    validate_entry_after_zone_creation,
    validate_planned_r_calculation,
    validate_minimum_r,
    run_integrity_checks,
    ViolationType,
    IntegrityReport,
)


class TestLookAheadDetection:
    """Test detection of look-ahead bias"""
    
    def test_valid_no_lookahead(self):
        """Test that valid trade (decision after zone creation) passes"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
            'zone_type': 'demand',
        }
        
        # Zone created at index 10, decision at index 15
        violation = validate_no_lookahead(
            trade=trade,
            zone_created_at_idx=10,
            zone_created_time=datetime(2024, 1, 1, 10, 0),
            decision_idx=15,
            decision_time=datetime(2024, 1, 1, 15, 0)
        )
        
        assert violation is None, "Valid trade should not trigger look-ahead violation"
    
    def test_lookahead_same_index(self):
        """Test that decision at same index as zone creation is flagged"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
        }
        
        # Zone created and decision at same index
        violation = validate_no_lookahead(
            trade=trade,
            zone_created_at_idx=10,
            zone_created_time=None,
            decision_idx=10,
            decision_time=None
        )
        
        assert violation is not None, "Decision at zone creation index should be flagged"
        assert violation.violation_type == ViolationType.LOOK_AHEAD
        assert "10" in violation.reason
    
    def test_lookahead_before_index(self):
        """Test that decision before zone creation is flagged"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
        }
        
        # Decision before zone creation
        violation = validate_no_lookahead(
            trade=trade,
            zone_created_at_idx=20,
            zone_created_time=None,
            decision_idx=15,
            decision_time=None
        )
        
        assert violation is not None, "Decision before zone creation should be flagged"
        assert violation.violation_type == ViolationType.LOOK_AHEAD
        assert "15" in violation.reason and "20" in violation.reason
    
    def test_lookahead_timestamp_check(self):
        """Test timestamp-based look-ahead detection"""
        trade = {
            'symbol': 'ETH/USDT',
            'entry_price': 3000,
        }
        
        zone_time = datetime(2024, 1, 1, 12, 0)
        decision_time = datetime(2024, 1, 1, 11, 0)  # Before zone creation
        
        violation = validate_no_lookahead(
            trade=trade,
            zone_created_at_idx=10,
            zone_created_time=zone_time,
            decision_idx=15,  # Index is OK
            decision_time=decision_time  # But time is not
        )
        
        assert violation is not None, "Decision before zone creation time should be flagged"
        assert violation.violation_type == ViolationType.LOOK_AHEAD
        assert "2024-01-01 11:00:00" in violation.reason


class TestEntryTimingValidation:
    """Test validation of entry timing relative to zone creation"""
    
    def test_valid_entry_after_creation(self):
        """Test that valid entry (after zone creation) passes"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
        }
        
        violation = validate_entry_after_zone_creation(
            trade=trade,
            zone_created_at_idx=10,
            zone_created_time=datetime(2024, 1, 1, 10, 0),
            entry_idx=20,
            entry_time=datetime(2024, 1, 1, 20, 0)
        )
        
        assert violation is None, "Entry after zone creation should pass"
    
    def test_entry_at_creation_index(self):
        """Test that entry at creation index is flagged"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
        }
        
        violation = validate_entry_after_zone_creation(
            trade=trade,
            zone_created_at_idx=10,
            zone_created_time=None,
            entry_idx=10,
            entry_time=None
        )
        
        assert violation is not None, "Entry at creation index should be flagged"
        assert violation.violation_type == ViolationType.ENTRY_BEFORE_ZONE
    
    def test_entry_before_creation(self):
        """Test that entry before zone creation is flagged"""
        trade = {
            'symbol': 'BTC/USDT',
            'entry_price': 50000,
        }
        
        violation = validate_entry_after_zone_creation(
            trade=trade,
            zone_created_at_idx=20,
            zone_created_time=None,
            entry_idx=15,
            entry_time=None
        )
        
        assert violation is not None, "Entry before zone creation should be flagged"
        assert violation.violation_type == ViolationType.ENTRY_BEFORE_ZONE


class TestRCalculationValidation:
    """Test validation of R multiple calculation"""
    
    def test_valid_r_calculation(self):
        """Test that correct R calculation passes"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 115.0,
            'r_multiple': 3.0,  # (115-100)/(100-95) = 15/5 = 3.0
        }
        
        violation = validate_planned_r_calculation(trade)
        
        assert violation is None, "Correct R calculation should pass"
    
    def test_r_calculation_mismatch(self):
        """Test that incorrect R calculation is flagged"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 115.0,
            'r_multiple': 2.5,  # Wrong! Should be 3.0
        }
        
        violation = validate_planned_r_calculation(trade)
        
        assert violation is not None, "Incorrect R calculation should be flagged"
        assert violation.violation_type == ViolationType.R_CALCULATION_MISMATCH
        # Check details instead of parsing reason string
        assert violation.details['recorded_r'] == 2.5
        assert abs(violation.details['expected_r'] - 3.0) < 0.01
    
    def test_r_calculation_short_trade(self):
        """Test R calculation for short trades"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 105.0,
            'take_profit': 85.0,
            'r_multiple': 3.0,  # (100-85)/(105-100) = 15/5 = 3.0
        }
        
        violation = validate_planned_r_calculation(trade)
        
        assert violation is None, "Correct R calculation for short should pass"
    
    def test_r_calculation_within_tolerance(self):
        """Test that small floating point errors within tolerance pass"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 115.0,
            'r_multiple': 3.005,  # Very close to 3.0 (0.5% error)
        }
        
        violation = validate_planned_r_calculation(trade, tolerance=0.01)
        
        assert violation is None, "R within tolerance should pass"
    
    def test_r_calculation_missing_fields(self):
        """Test that missing fields are flagged"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 95.0,
            # Missing take_profit and r_multiple
        }
        
        violation = validate_planned_r_calculation(trade)
        
        assert violation is not None, "Missing fields should be flagged"
        assert violation.violation_type == ViolationType.R_CALCULATION_MISMATCH
    
    def test_r_calculation_zero_risk(self):
        """Test that zero risk (entry = stop) is flagged"""
        trade = {
            'entry_price': 100.0,
            'stop_loss': 100.0,  # Same as entry!
            'take_profit': 115.0,
            'r_multiple': 999.0,
        }
        
        violation = validate_planned_r_calculation(trade)
        
        assert violation is not None, "Zero risk should be flagged"
        assert violation.violation_type == ViolationType.R_CALCULATION_MISMATCH
        assert "zero" in violation.reason.lower()


class TestMinimumRValidation:
    """Test validation of minimum R requirement"""
    
    def test_valid_minimum_r(self):
        """Test that R above minimum passes"""
        trade = {
            'r_multiple': 3.5,
            'planned_r': 3.5,
        }
        
        violation = validate_minimum_r(trade, min_r=3.0)
        
        assert violation is None, "R above minimum should pass"
    
    def test_r_exactly_at_minimum(self):
        """Test that R exactly at minimum passes"""
        trade = {
            'r_multiple': 3.0,
            'planned_r': 3.0,
        }
        
        violation = validate_minimum_r(trade, min_r=3.0)
        
        assert violation is None, "R exactly at minimum should pass"
    
    def test_r_below_minimum(self):
        """Test that R below minimum is flagged"""
        trade = {
            'r_multiple': 2.5,
            'planned_r': 2.5,
        }
        
        violation = validate_minimum_r(trade, min_r=3.0)
        
        assert violation is not None, "R below minimum should be flagged"
        assert violation.violation_type == ViolationType.INSUFFICIENT_R
        # Check details instead of parsing reason string
        assert violation.details['planned_r'] == 2.5
        assert violation.details['min_r'] == 3.0
    
    def test_r_missing_field(self):
        """Test that missing R field is flagged"""
        trade = {
            'entry_price': 100.0,
            # Missing r_multiple
        }
        
        violation = validate_minimum_r(trade, min_r=3.0)
        
        assert violation is not None, "Missing R should be flagged"
        assert violation.violation_type == ViolationType.INSUFFICIENT_R


class TestIntegrityReportGeneration:
    """Test complete integrity report generation"""
    
    def test_clean_report(self):
        """Test report for clean trades with no violations"""
        trades = [
            {
                'symbol': 'BTC/USDT',
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 10,
                'decision_idx': 15,
                'entry_idx': 20,
            },
            {
                'symbol': 'ETH/USDT',
                'entry_price': 200.0,
                'stop_loss': 190.0,
                'take_profit': 230.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 5,
                'decision_idx': 10,
                'entry_idx': 15,
            },
        ]
        
        report = run_integrity_checks(trades)
        
        assert report.total_trades == 2
        assert report.clean is True
        assert len(report.violations) == 0
        assert all(count == 0 for count in report.violation_counts.values())
    
    def test_report_with_violations(self):
        """Test report with multiple types of violations"""
        trades = [
            # Clean trade
            {
                'symbol': 'BTC/USDT',
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 10,
                'decision_idx': 15,
                'entry_idx': 20,
            },
            # Look-ahead violation
            {
                'symbol': 'ETH/USDT',
                'entry_price': 200.0,
                'stop_loss': 190.0,
                'take_profit': 230.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 20,
                'decision_idx': 15,  # Before zone creation!
                'entry_idx': 25,
            },
            # Insufficient R violation
            {
                'symbol': 'SOL/USDT',
                'entry_price': 50.0,
                'stop_loss': 48.0,
                'take_profit': 54.0,
                'r_multiple': 2.0,  # Below minimum 3.0
                'zone_created_at_idx': 10,
                'decision_idx': 15,
                'entry_idx': 20,
            },
            # R calculation mismatch
            {
                'symbol': 'ADA/USDT',
                'entry_price': 1.0,
                'stop_loss': 0.95,
                'take_profit': 1.15,
                'r_multiple': 2.5,  # Wrong! Should be 3.0
                'zone_created_at_idx': 10,
                'decision_idx': 15,
                'entry_idx': 20,
            },
        ]
        
        report = run_integrity_checks(trades)
        
        assert report.total_trades == 4
        assert report.clean is False
        assert len(report.violations) >= 3  # At least 3 violations
        assert report.violation_counts[ViolationType.LOOK_AHEAD] >= 1
        assert report.violation_counts[ViolationType.INSUFFICIENT_R] >= 1
        assert report.violation_counts[ViolationType.R_CALCULATION_MISMATCH] >= 1
    
    def test_report_counts_violations_correctly(self):
        """Test that violation counts are accurate"""
        trades = [
            # Two look-ahead violations (decision before zone creation)
            {
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 20,
                'decision_idx': 15,  # Before zone creation - look-ahead violation
                'entry_idx': 16,  # Also before zone creation - entry violation
            },
            {
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': 115.0,
                'r_multiple': 3.0,
                'zone_created_at_idx': 30,
                'decision_idx': 25,  # Before zone creation - look-ahead violation
                'entry_idx': 26,  # Also before zone creation - entry violation
            },
        ]
        
        report = run_integrity_checks(trades)
        
        assert report.total_trades == 2
        assert report.clean is False
        # Each trade violates look-ahead in decision check
        assert report.violation_counts[ViolationType.LOOK_AHEAD] >= 2
        # Each trade also violates entry timing
        assert report.violation_counts[ViolationType.ENTRY_BEFORE_ZONE] >= 2


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_intentional_lookahead_scenario(self):
        """Test that we can detect an intentional look-ahead bug in backtest code
        
        This simulates a common mistake where someone uses a zone for trading
        decisions before it has fully formed (before leg-out completes).
        """
        # Scenario: Zone forms from candles 10-15 (created at idx 15)
        # But backtest code mistakenly uses it at candle 12
        trade = {
            'symbol': 'BTC/USDT',
            'entry_time': datetime(2024, 1, 1, 12, 0),
            'entry_price': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 53000.0,
            'r_multiple': 3.0,
            'zone_created_at_idx': 15,  # Zone completes here
            'decision_idx': 12,  # But decision was made here (BUG!)
            'entry_idx': 13,  # Entry also before completion
        }
        
        report = run_integrity_checks([trade])
        
        # Should detect both look-ahead violations
        assert not report.clean, "Look-ahead bug should be detected"
        assert report.violation_counts[ViolationType.LOOK_AHEAD] >= 1
        assert report.violation_counts[ViolationType.ENTRY_BEFORE_ZONE] >= 1
        
        # Verify the violation details
        lookahead_violations = [
            v for v in report.violations 
            if v.violation_type == ViolationType.LOOK_AHEAD
        ]
        assert len(lookahead_violations) > 0
        assert '12' in lookahead_violations[0].reason
        assert '15' in lookahead_violations[0].reason
    
    def test_realistic_clean_backtest(self):
        """Test a realistic scenario with multiple clean trades"""
        # Simulate 5 trades with proper timing and R values
        trades = []
        for i in range(5):
            zone_idx = i * 20
            decision_idx = zone_idx + 5
            entry_idx = zone_idx + 10
            
            trades.append({
                'symbol': 'BTC/USDT' if i % 2 == 0 else 'ETH/USDT',
                'entry_price': 50000.0 + i * 1000,
                'stop_loss': 49000.0 + i * 1000,
                'take_profit': 53000.0 + i * 1000,
                'r_multiple': 3.0,
                'zone_created_at_idx': zone_idx,
                'zone_created_time': datetime(2024, 1, 1) + timedelta(hours=zone_idx),
                'decision_idx': decision_idx,
                'decision_time': datetime(2024, 1, 1) + timedelta(hours=decision_idx),
                'entry_idx': entry_idx,
                'entry_time': datetime(2024, 1, 1) + timedelta(hours=entry_idx),
            })
        
        report = run_integrity_checks(trades)
        
        assert report.total_trades == 5
        assert report.clean is True
        assert len(report.violations) == 0
