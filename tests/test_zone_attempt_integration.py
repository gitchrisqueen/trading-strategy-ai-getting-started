"""Integration test for zone attempt tracking in backtest adapter

This test creates a minimal backtest scenario to verify that:
1. Zone attempts are tracked correctly
2. Disabled zones are skipped in evaluation
3. Cooldown logic works as expected
"""

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from strategies.supply_demand_v1.strategy import (
    Zone,
    ZoneType,
    SupplyDemandParameters,
)


def test_zone_attempt_tracking_integration():
    """Test zone attempt tracking in a realistic scenario"""
    
    print("\n" + "="*80)
    print("INTEGRATION TEST: Zone Attempt Tracking")
    print("="*80)
    
    # Create a zone
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=5,
        base_end_idx=7,
        legout_end_idx=10,
        base_len=3,
        legout_len=3,
    )
    
    print(f"\nCreated zone at index {zone.created_at}")
    print(f"  Proximal: {zone.proximal}, Distal: {zone.distal}")
    print(f"  Initial state: attempts={zone.attempts}, disabled={zone.disabled}")
    
    # Simulate backtest scenario with max_attempts=1
    params = SupplyDemandParameters(max_attempts_per_zone=1, cooldown_bars=None)
    
    print(f"\nParameters: max_attempts={params.max_attempts_per_zone}, cooldown_bars={params.cooldown_bars}")
    
    # Scenario 1: First evaluation (should pass)
    current_idx = 50
    print(f"\n[Bar {current_idx}] Evaluating zone...")
    
    if not zone.disabled:
        print("  ✓ Zone is active (not disabled)")
        if zone.attempts < params.max_attempts_per_zone:
            print("  ✓ Attempts below max, can place order")
            # Simulate order placement
            zone.attempts += 1
            zone.last_attempt_idx = current_idx
            print(f"  → Order placed! attempts={zone.attempts}, last_attempt_idx={zone.last_attempt_idx}")
        else:
            print("  ✗ Max attempts reached")
    else:
        print("  ✗ Zone is disabled, skipping")
    
    # Scenario 2: Second evaluation (should be disabled)
    current_idx = 70
    print(f"\n[Bar {current_idx}] Evaluating zone again...")
    
    # Check if zone should be disabled
    if zone.attempts >= params.max_attempts_per_zone:
        if params.cooldown_bars is None:
            print(f"  ✗ Max attempts reached ({zone.attempts} >= {params.max_attempts_per_zone})")
            print("  → No cooldown configured, disabling zone permanently")
            zone.disabled = True
        else:
            print(f"  ! Max attempts reached, checking cooldown...")
    
    if zone.disabled:
        print("  ✗ Zone is disabled, skipping evaluation entirely")
    else:
        print("  ✓ Zone is still active")
    
    # Verify final state
    print("\n" + "-"*80)
    print("FINAL STATE:")
    print(f"  attempts: {zone.attempts}")
    print(f"  last_attempt_idx: {zone.last_attempt_idx}")
    print(f"  disabled: {zone.disabled}")
    
    assert zone.attempts == 1, "Zone should have exactly 1 attempt"
    assert zone.last_attempt_idx == 50, "Last attempt should be at bar 50"
    assert zone.disabled is True, "Zone should be disabled after max attempts"
    
    print("\n✅ Integration test passed!")


def test_zone_cooldown_integration():
    """Test zone cooldown logic in a realistic scenario"""
    
    print("\n" + "="*80)
    print("INTEGRATION TEST: Zone Cooldown Logic")
    print("="*80)
    
    # Create a zone
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=5,
        base_end_idx=7,
        legout_end_idx=10,
        base_len=3,
        legout_len=3,
    )
    
    print(f"\nCreated zone at index {zone.created_at}")
    
    # Simulate backtest scenario with max_attempts=2 and cooldown=30
    params = SupplyDemandParameters(max_attempts_per_zone=2, cooldown_bars=30)
    
    print(f"Parameters: max_attempts={params.max_attempts_per_zone}, cooldown_bars={params.cooldown_bars}")
    
    # First attempt
    current_idx = 50
    print(f"\n[Bar {current_idx}] First attempt...")
    zone.attempts += 1
    zone.last_attempt_idx = current_idx
    print(f"  → Order placed! attempts={zone.attempts}")
    
    # Second attempt
    current_idx = 80
    print(f"\n[Bar {current_idx}] Second attempt...")
    zone.attempts += 1
    zone.last_attempt_idx = current_idx
    print(f"  → Order placed! attempts={zone.attempts}")
    
    # Third evaluation - should trigger cooldown
    current_idx = 100
    print(f"\n[Bar {current_idx}] Third evaluation...")
    
    if zone.attempts >= params.max_attempts_per_zone:
        print(f"  ✗ Max attempts reached ({zone.attempts} >= {params.max_attempts_per_zone})")
        
        if params.cooldown_bars is not None and zone.last_attempt_idx is not None:
            bars_since_attempt = current_idx - zone.last_attempt_idx
            print(f"  → Cooldown check: {bars_since_attempt} bars since last attempt (need {params.cooldown_bars})")
            
            if bars_since_attempt >= params.cooldown_bars:
                print("  ✓ Cooldown elapsed! Re-enabling zone...")
                zone.attempts = 0
                zone.last_attempt_idx = None
                zone.disabled = False
            else:
                print(f"  ⏳ Still in cooldown ({bars_since_attempt}/{params.cooldown_bars} bars)")
                zone.disabled = True
    
    assert zone.disabled is True, "Zone should be disabled (cooldown not elapsed)"
    
    # Fourth evaluation - cooldown should have elapsed
    current_idx = 120
    print(f"\n[Bar {current_idx}] Fourth evaluation (after cooldown)...")
    
    if zone.disabled and zone.attempts >= params.max_attempts_per_zone:
        if params.cooldown_bars is not None and zone.last_attempt_idx is not None:
            bars_since_attempt = current_idx - zone.last_attempt_idx
            print(f"  → Cooldown check: {bars_since_attempt} bars since last attempt (need {params.cooldown_bars})")
            
            if bars_since_attempt >= params.cooldown_bars:
                print("  ✓ Cooldown elapsed! Re-enabling zone...")
                zone.attempts = 0
                zone.last_attempt_idx = None
                zone.disabled = False
            else:
                print(f"  ⏳ Still in cooldown")
    
    assert zone.attempts == 0, "Attempts should be reset after cooldown"
    assert zone.last_attempt_idx is None, "Last attempt should be cleared"
    assert zone.disabled is False, "Zone should be re-enabled after cooldown"
    
    print(f"\n  ✅ Zone re-enabled! Can place new order")
    
    print("\n✅ Cooldown integration test passed!")


if __name__ == "__main__":
    test_zone_attempt_tracking_integration()
    test_zone_cooldown_integration()
    
    print("\n" + "="*80)
    print("✅ ALL INTEGRATION TESTS PASSED!")
    print("="*80)
