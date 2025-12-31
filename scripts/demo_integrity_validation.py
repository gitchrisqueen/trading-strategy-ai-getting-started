#!/usr/bin/env python3
"""
Demo: Backtest Integrity Validation

This script demonstrates the backtest integrity validation system with both
clean and intentionally flawed scenarios.
"""

import sys
import os
from datetime import datetime, timedelta

# Add repository root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from strategies.supply_demand_v1.integrity import (
    run_integrity_checks,
    print_integrity_report,
)


def demo_clean_backtest():
    """Demonstrate a clean backtest with no violations"""
    print("\n" + "="*80)
    print("DEMO 1: Clean Backtest (No Violations)")
    print("="*80)
    
    trades = [
        {
            'symbol': 'BTC/USDT',
            'entry_time': datetime(2024, 1, 1, 15, 0),
            'entry_price': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 53000.0,
            'r_multiple': 3.0,
            'planned_r': 3.0,
            'outcome_r': 3.0,
            'zone_type': 'demand',
            # Proper timing: zone created at 10, decision at 11, entry at 15
            'zone_created_at_idx': 10,
            'zone_created_time': datetime(2024, 1, 1, 10, 0),
            'decision_idx': 11,
            'decision_time': datetime(2024, 1, 1, 11, 0),
            'entry_idx': 15,
        },
        {
            'symbol': 'ETH/USDT',
            'entry_time': datetime(2024, 1, 2, 18, 0),
            'entry_price': 3000.0,
            'stop_loss': 2900.0,
            'take_profit': 3300.0,
            'r_multiple': 3.0,
            'planned_r': 3.0,
            'outcome_r': -1.0,  # Lost this one
            'zone_type': 'demand',
            # Proper timing
            'zone_created_at_idx': 50,
            'zone_created_time': datetime(2024, 1, 2, 12, 0),
            'decision_idx': 52,
            'decision_time': datetime(2024, 1, 2, 13, 0),
            'entry_idx': 60,
        },
    ]
    
    report = run_integrity_checks(trades)
    print_integrity_report(report, verbose=False)
    
    if report.clean:
        print("\n✓ This backtest maintains proper standards!")


def demo_lookahead_bias():
    """Demonstrate detection of look-ahead bias"""
    print("\n" + "="*80)
    print("DEMO 2: Look-Ahead Bias Detected")
    print("="*80)
    print("Scenario: Trading decision made before zone completion")
    
    trades = [
        {
            'symbol': 'BTC/USDT',
            'entry_time': datetime(2024, 1, 1, 15, 0),
            'entry_price': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 53000.0,
            'r_multiple': 3.0,
            'planned_r': 3.0,
            'zone_type': 'demand',
            # BUG: Decision made BEFORE zone creation!
            'zone_created_at_idx': 20,
            'zone_created_time': datetime(2024, 1, 1, 20, 0),
            'decision_idx': 15,  # Too early!
            'decision_time': datetime(2024, 1, 1, 15, 0),
            'entry_idx': 25,
        },
    ]
    
    report = run_integrity_checks(trades)
    print_integrity_report(report, verbose=True)


def demo_r_calculation_error():
    """Demonstrate detection of R calculation errors"""
    print("\n" + "="*80)
    print("DEMO 3: R Calculation Mismatch Detected")
    print("="*80)
    print("Scenario: Incorrect R calculation in trade plan")
    
    trades = [
        {
            'symbol': 'SOL/USDT',
            'entry_time': datetime(2024, 1, 1, 15, 0),
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 110.0,
            'r_multiple': 2.5,  # BUG: Should be 2.0!
            'planned_r': 2.5,
            'zone_type': 'demand',
            'zone_created_at_idx': 10,
            'decision_idx': 11,
            'entry_idx': 15,
        },
    ]
    
    report = run_integrity_checks(trades)
    print_integrity_report(report, verbose=True)
    
    print("\nExpected R calculation:")
    print("  Risk:   |100 - 95|  = 5")
    print("  Reward: |110 - 100| = 10")
    print("  R = 10 / 5 = 2.0")
    print("  But recorded R = 2.5 (WRONG!)")


def demo_insufficient_r():
    """Demonstrate detection of trades below minimum R"""
    print("\n" + "="*80)
    print("DEMO 4: Insufficient R Detected")
    print("="*80)
    print("Scenario: Trade plan with R below minimum 3.0 requirement")
    
    trades = [
        {
            'symbol': 'ADA/USDT',
            'entry_time': datetime(2024, 1, 1, 15, 0),
            'entry_price': 1.0,
            'stop_loss': 0.95,
            'take_profit': 1.10,
            'r_multiple': 2.0,  # Below minimum 3.0!
            'planned_r': 2.0,
            'zone_type': 'demand',
            'zone_created_at_idx': 10,
            'decision_idx': 11,
            'entry_idx': 15,
        },
    ]
    
    report = run_integrity_checks(trades, min_r=3.0)
    print_integrity_report(report, verbose=True)
    
    print("\nStrategy requires minimum 3R for positive expectancy.")
    print("This trade only offers 2R - violates strategy rules!")


def demo_multiple_violations():
    """Demonstrate multiple violation types in one backtest"""
    print("\n" + "="*80)
    print("DEMO 5: Multiple Violations in One Backtest")
    print("="*80)
    
    trades = [
        # Clean trade
        {
            'symbol': 'BTC/USDT',
            'entry_price': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 53000.0,
            'r_multiple': 3.0,
            'zone_created_at_idx': 10,
            'decision_idx': 11,
            'entry_idx': 15,
        },
        # Look-ahead violation
        {
            'symbol': 'ETH/USDT',
            'entry_price': 3000.0,
            'stop_loss': 2900.0,
            'take_profit': 3300.0,
            'r_multiple': 3.0,
            'zone_created_at_idx': 20,
            'decision_idx': 18,  # Before creation!
            'entry_idx': 25,
        },
        # R calculation error
        {
            'symbol': 'SOL/USDT',
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 115.0,
            'r_multiple': 2.0,  # Wrong! Should be 3.0
            'zone_created_at_idx': 30,
            'decision_idx': 31,
            'entry_idx': 35,
        },
        # Insufficient R
        {
            'symbol': 'ADA/USDT',
            'entry_price': 1.0,
            'stop_loss': 0.9,
            'take_profit': 1.15,
            'r_multiple': 1.5,  # Below minimum!
            'zone_created_at_idx': 40,
            'decision_idx': 41,
            'entry_idx': 45,
        },
    ]
    
    report = run_integrity_checks(trades)
    print_integrity_report(report, verbose=False)
    
    print(f"\nSummary: {len(report.violations)} violations found in {report.total_trades} trades")
    print("Clean trades: 1/4 (25%)")


if __name__ == '__main__':
    print("\n" + "="*80)
    print("BACKTEST INTEGRITY VALIDATION DEMOS")
    print("="*80)
    print("\nThese demos show how the integrity validation system works.")
    print("It checks for common backtest flaws that lead to unrealistic results.")
    
    demo_clean_backtest()
    demo_lookahead_bias()
    demo_r_calculation_error()
    demo_insufficient_r()
    demo_multiple_violations()
    
    print("\n" + "="*80)
    print("DEMOS COMPLETE")
    print("="*80)
    print("\nFor more information, see:")
    print("  - strategies/supply_demand_v1/integrity.py (implementation)")
    print("  - strategies/supply_demand_v1/INTEGRITY_REPORT.md (documentation)")
    print("  - tests/test_supply_demand_integrity.py (unit tests)")
    print("  - notebooks/supply_demand_v1_backtest.ipynb (notebook example)")
    print()
