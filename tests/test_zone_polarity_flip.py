"""Tests for dynamic zone polarity flipping

This test validates zones can flip between Supply and Demand multiple times
based on price crossing their distal boundary.
"""

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from strategies.supply_demand_v1.strategy import (
    Zone,
    ZoneType,
    initialize_zone_polarity,
    check_polarity_flip,
    get_zone_polarity_at_idx,
)


def test_initialize_zone_polarity():
    """Test that polarity fields are initialized correctly"""
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    
    # Initially polarity fields should be None
    assert zone.original_type is None
    assert zone.polarity_type is None
    
    # Initialize polarity
    initialize_zone_polarity(zone)
    
    # After initialization, polarity should match detection type
    assert zone.original_type == ZoneType.DEMAND
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.flip_count == 0
    assert zone.last_flip_idx is None
    
    print("✓ test_initialize_zone_polarity passed")


def test_polarity_flip_demand_to_supply():
    """Test DEMAND zone flipping to SUPPLY when price breaks below distal"""
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,  # Flip boundary
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Price moves from above distal to below distal (decisive break)
    prev_close = 96.0  # Above distal
    current_close = 94.0  # Below distal
    current_idx = 20
    
    # Check for flip
    flipped = check_polarity_flip(zone, current_idx, current_close, prev_close)
    
    # Should flip from DEMAND to SUPPLY
    assert flipped is True
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 1
    assert zone.last_flip_idx == 20
    
    print("✓ test_polarity_flip_demand_to_supply passed")


def test_polarity_flip_supply_to_demand():
    """Test SUPPLY zone flipping to DEMAND when price breaks above distal"""
    zone = Zone(
        zone_type=ZoneType.SUPPLY,
        proximal=95.0,
        distal=100.0,  # Flip boundary
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Price moves from below distal to above distal (decisive break)
    prev_close = 99.0  # Below distal
    current_close = 101.0  # Above distal
    current_idx = 20
    
    # Check for flip
    flipped = check_polarity_flip(zone, current_idx, current_close, prev_close)
    
    # Should flip from SUPPLY to DEMAND
    assert flipped is True
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.flip_count == 1
    assert zone.last_flip_idx == 20
    
    print("✓ test_polarity_flip_supply_to_demand passed")


def test_polarity_multiple_flips():
    """Test zone can flip multiple times (Supply→Demand→Supply→Demand)"""
    zone = Zone(
        zone_type=ZoneType.SUPPLY,
        proximal=95.0,
        distal=100.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 0
    
    # Flip 1: SUPPLY → DEMAND (price breaks above distal)
    flipped = check_polarity_flip(zone, 20, 101.0, 99.0)
    assert flipped is True
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.flip_count == 1
    
    # Flip 2: DEMAND → SUPPLY (price breaks below distal)
    flipped = check_polarity_flip(zone, 30, 99.0, 101.0)
    assert flipped is True
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 2
    
    # Flip 3: SUPPLY → DEMAND (price breaks above distal again)
    flipped = check_polarity_flip(zone, 40, 102.0, 98.0)
    assert flipped is True
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.flip_count == 3
    
    print("✓ test_polarity_multiple_flips passed")


def test_polarity_no_flip_without_cross():
    """Test that polarity doesn't flip unless price crosses distal"""
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Case 1: Both closes above distal (no cross)
    flipped = check_polarity_flip(zone, 20, 97.0, 96.0)
    assert flipped is False
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.flip_count == 0
    
    # Case 2: Both closes below distal (no cross)
    # First, flip to SUPPLY
    flipped = check_polarity_flip(zone, 21, 94.0, 96.0)
    assert flipped is True
    assert zone.polarity_type == ZoneType.SUPPLY
    
    # Now both below, no flip
    flipped = check_polarity_flip(zone, 22, 93.0, 94.0)
    assert flipped is False
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 1  # Still only 1 flip
    
    print("✓ test_polarity_no_flip_without_cross passed")


def test_get_zone_polarity_at_idx():
    """Test getting polarity at specific index"""
    zone = Zone(
        zone_type=ZoneType.SUPPLY,
        proximal=95.0,
        distal=100.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Before any flips, polarity should be original type
    assert get_zone_polarity_at_idx(zone, 15) == ZoneType.SUPPLY
    
    # Flip at index 20
    check_polarity_flip(zone, 20, 101.0, 99.0)
    
    # After flip, polarity at later indices should reflect the flip
    assert get_zone_polarity_at_idx(zone, 25) == ZoneType.DEMAND
    
    print("✓ test_get_zone_polarity_at_idx passed")


def test_polarity_flip_scenario_realistic():
    """Test realistic multi-flip scenario simulating price action"""
    # Scenario: DEMAND zone at 95-100, price oscillates around distal (100)
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Candle series simulating price action
    candles = [
        {'idx': 15, 'close': 97.0, 'prev_close': 98.0},  # Within zone, no flip
        {'idx': 16, 'close': 96.0, 'prev_close': 97.0},  # Still within, no flip
        {'idx': 17, 'close': 94.0, 'prev_close': 96.0},  # Crosses below distal (95) → FLIP to SUPPLY
        {'idx': 18, 'close': 93.0, 'prev_close': 94.0},  # Below, no flip
        {'idx': 19, 'close': 96.0, 'prev_close': 93.0},  # Crosses above distal → FLIP to DEMAND
        {'idx': 20, 'close': 98.0, 'prev_close': 96.0},  # Above, no flip
        {'idx': 21, 'close': 94.5, 'prev_close': 98.0}, # Crosses below distal → FLIP to SUPPLY
        {'idx': 22, 'close': 96.5, 'prev_close': 94.5}, # Crosses above distal → FLIP to DEMAND
    ]
    
    expected_flips = [
        (17, ZoneType.SUPPLY),  # First flip
        (19, ZoneType.DEMAND),  # Second flip
        (21, ZoneType.SUPPLY),  # Third flip
        (22, ZoneType.DEMAND),  # Fourth flip
    ]
    
    flip_results = []
    for candle in candles:
        flipped = check_polarity_flip(
            zone,
            candle['idx'],
            candle['close'],
            candle['prev_close']
        )
        if flipped:
            flip_results.append((candle['idx'], zone.polarity_type))
    
    # Verify flips match expected
    assert len(flip_results) == len(expected_flips), f"Expected {len(expected_flips)} flips, got {len(flip_results)}"
    for i, (expected_idx, expected_type) in enumerate(expected_flips):
        actual_idx, actual_type = flip_results[i]
        assert actual_idx == expected_idx, f"Flip {i+1}: expected at idx {expected_idx}, got {actual_idx}"
        assert actual_type == expected_type, f"Flip {i+1}: expected {expected_type}, got {actual_type}"
    
    # Final state
    assert zone.flip_count == 4
    assert zone.polarity_type == ZoneType.DEMAND
    assert zone.last_flip_idx == 22
    
    print("✓ test_polarity_flip_scenario_realistic passed")


def test_polarity_preserved_across_checks():
    """Test that polarity state is preserved when checking same idx multiple times"""
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=10,
        base_start_idx=8,
        base_end_idx=9,
        legout_end_idx=10,
        base_len=2,
        legout_len=1,
    )
    initialize_zone_polarity(zone)
    
    # Flip zone
    check_polarity_flip(zone, 20, 94.0, 96.0)
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 1
    
    # Check same index again (should not flip again)
    check_polarity_flip(zone, 20, 94.0, 96.0)
    assert zone.polarity_type == ZoneType.SUPPLY
    assert zone.flip_count == 1  # Should still be 1
    
    print("✓ test_polarity_preserved_across_checks passed")


if __name__ == "__main__":
    # Run all tests
    test_initialize_zone_polarity()
    test_polarity_flip_demand_to_supply()
    test_polarity_flip_supply_to_demand()
    test_polarity_multiple_flips()
    test_polarity_no_flip_without_cross()
    test_get_zone_polarity_at_idx()
    test_polarity_flip_scenario_realistic()
    test_polarity_preserved_across_checks()
    
    print("\n✅ All polarity flip tests passed!")
