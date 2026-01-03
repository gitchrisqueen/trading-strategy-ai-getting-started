"""Tests for time-relative zone freshness behavior

This test suite validates that zone freshness is correctly computed as-of
any candle index, not just as a final "ever touched" state.
"""

import pytest
from strategies.supply_demand_v1.strategy import Zone, ZoneType
from strategies.supply_demand_v1.zone_freshness_precompute import (
    precompute_zone_freshness,
    is_zone_fresh_at_idx,
)


class TestTimeRelativeFreshness:
    """Test that freshness is time-relative, not just a final state"""
    
    def test_freshness_before_touch(self):
        """Zone should be fresh at indices before first touch"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        candles = [
            {'low': 90, 'high': 110},   # idx 0: Zone creation
            {'low': 110, 'high': 115},  # idx 1: Away from zone
            {'low': 110, 'high': 115},  # idx 2: Still away
            {'low': 96, 'high': 102},   # idx 3: First touch
            {'low': 110, 'high': 115},  # idx 4: Away again
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Verify precomputed state
        assert zone.first_touch_idx == 3
        assert zone.ever_touched is True
        assert zone.freshness_touches == 1
        
        # Verify time-relative freshness
        assert is_zone_fresh_at_idx(zone, 0) == True, "Should be fresh at creation"
        assert is_zone_fresh_at_idx(zone, 1) == True, "Should be fresh before touch"
        assert is_zone_fresh_at_idx(zone, 2) == True, "Should be fresh before touch"
        assert is_zone_fresh_at_idx(zone, 3) == False, "Should NOT be fresh at touch"
        assert is_zone_fresh_at_idx(zone, 4) == False, "Should NOT be fresh after touch"
    
    def test_freshness_never_touched(self):
        """Zone that's never touched should always be fresh"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        candles = [
            {'low': 90, 'high': 110},   # idx 0: Zone creation
            {'low': 110, 'high': 115},  # idx 1: Away
            {'low': 110, 'high': 115},  # idx 2: Away
            {'low': 110, 'high': 115},  # idx 3: Still away
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Verify precomputed state
        assert zone.first_touch_idx is None
        assert zone.ever_touched is False
        assert zone.freshness_touches == 0
        
        # Verify time-relative freshness - should be fresh at ALL indices
        for idx in range(len(candles)):
            assert is_zone_fresh_at_idx(zone, idx) == True, f"Should be fresh at idx {idx}"
    
    def test_freshness_created_but_not_active_yet(self):
        """Zone created at idx X should not be considered fresh at indices < X"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=5,  # Created at index 5
            base_start_idx=3,
            base_end_idx=4,
            legout_end_idx=5,
            base_len=2,
            legout_len=1,
        )
        
        candles = [
            {'low': 90, 'high': 110},   # idx 0
            {'low': 110, 'high': 115},  # idx 1
            {'low': 110, 'high': 115},  # idx 2
            {'low': 100, 'high': 105},  # idx 3: base start
            {'low': 99, 'high': 101},   # idx 4: base end
            {'low': 101, 'high': 110},  # idx 5: legout end (zone created)
            {'low': 110, 'high': 115},  # idx 6: Away from zone
            {'low': 96, 'high': 102},   # idx 7: First touch
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Verify precomputed state
        assert zone.first_touch_idx == 7
        assert zone.ever_touched is True
        
        # Verify time-relative freshness
        # Zone is fresh from creation (idx 5) until first touch (idx 7)
        assert is_zone_fresh_at_idx(zone, 5) == True, "Fresh at creation"
        assert is_zone_fresh_at_idx(zone, 6) == True, "Fresh before touch"
        assert is_zone_fresh_at_idx(zone, 7) == False, "Not fresh at touch"
    
    def test_multiple_zones_different_freshness(self):
        """Multiple zones should have independent freshness states"""
        zone1 = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        zone2 = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=85,
            distal=90,
            created_at=2,
            base_start_idx=2,
            base_end_idx=3,
            legout_end_idx=4,
            base_len=2,
            legout_len=1,
        )
        
        candles = [
            {'low': 90, 'high': 110},   # idx 0: Zone1 creation
            {'low': 110, 'high': 115},  # idx 1: Away from both zones
            {'low': 110, 'high': 115},  # idx 2: Zone2 creation, Zone1 still fresh
            {'low': 110, 'high': 115},  # idx 3: Away from both zones  
            {'low': 96, 'high': 102},   # idx 4: Zone1 touched, Zone2 still fresh
            {'low': 84, 'high': 91},    # idx 5: Zone2 touched
        ]
        
        precompute_zone_freshness([zone1, zone2], candles)
        
        # Verify zone1 freshness over time
        assert is_zone_fresh_at_idx(zone1, 0) == True
        assert is_zone_fresh_at_idx(zone1, 3) == True
        assert is_zone_fresh_at_idx(zone1, 4) == False  # Touched at idx 4
        assert is_zone_fresh_at_idx(zone1, 5) == False
        
        # Verify zone2 freshness over time
        assert is_zone_fresh_at_idx(zone2, 2) == True
        assert is_zone_fresh_at_idx(zone2, 4) == True
        assert is_zone_fresh_at_idx(zone2, 5) == False  # Touched at idx 5
    
    def test_deprecated_is_fresh_field(self):
        """Test that deprecated is_fresh field matches ever_touched (inverted)"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        candles = [
            {'low': 90, 'high': 110},   # idx 0: Zone creation
            {'low': 110, 'high': 115},  # idx 1: Away
            {'low': 96, 'high': 102},   # idx 2: Touch
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Deprecated is_fresh should be opposite of ever_touched
        assert zone.is_fresh == (not zone.ever_touched)
        assert zone.is_fresh is False  # Ever touched, so not fresh
        assert zone.ever_touched is True


class TestDecisionFunnelConsistency:
    """Test that decision funnel counts match zones.csv counts"""
    
    def test_fresh_count_at_simulation_start(self):
        """Fresh zone count should match zones that are fresh at simulation start"""
        zones = [
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=100,
                distal=95,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=2,
                legout_len=1,
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=110,
                distal=105,
                created_at=5,
                base_start_idx=5,
                base_end_idx=6,
                legout_end_idx=7,
                base_len=2,
                legout_len=1,
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=120,
                distal=115,
                created_at=150,  # Created after simulation start
                base_start_idx=150,
                base_end_idx=151,
                legout_end_idx=152,
                base_len=2,
                legout_len=1,
            ),
        ]
        
        # Create non-overlapping candles
        candles = []
        for _ in range(200):
            # Candles that don't overlap with any zones
            candles.append({'low': 130, 'high': 140})
        
        # Touch zone 0 at idx 10
        candles[10] = {'low': 95, 'high': 102}  # Overlaps zone 0 (100-95)
        # Zone 1 (110-105) is never touched (candles stay at 130-140)
        # Zone 2 (120-115) is never touched
        
        precompute_zone_freshness(zones, candles)
        
        simulation_start_idx = 100  # Typical simulation start
        
        # Count fresh zones at simulation start
        fresh_at_start = sum(
            1 for z in zones 
            if z.created_at <= simulation_start_idx 
            and is_zone_fresh_at_idx(z, simulation_start_idx)
        )
        
        # Zone 0: created at 0, touched at 10 -> NOT fresh at 100
        # Zone 1: created at 5, never touched -> fresh at 100
        # Zone 2: created at 150 -> not created yet at 100
        assert fresh_at_start == 1  # Only zone 1 is fresh at start
        
        # Compare to final freshness
        final_idx = len(candles) - 1
        fresh_at_end = sum(
            1 for z in zones
            if z.created_at <= final_idx
            and is_zone_fresh_at_idx(z, final_idx)
        )
        
        # At end: zone 0 not fresh, zone 1 fresh, zone 2 fresh
        assert fresh_at_end == 2
        
        # Verify that initial count != final count (proving time-relativity)
        assert fresh_at_start != fresh_at_end


class TestWindowCorrectness:
    """Test that precompute is called on correct candle window"""
    
    def test_precompute_matches_simulation_window(self):
        """Precompute should use same candle list as simulation"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        # Full candle list
        full_candles = [
            {'low': 90, 'high': 110},   # idx 0
            {'low': 110, 'high': 115},  # idx 1
            {'low': 96, 'high': 102},   # idx 2: Touch
            {'low': 110, 'high': 115},  # idx 3
            {'low': 110, 'high': 115},  # idx 4
        ]
        
        # Simulate slicing by date (runner might do this)
        sliced_candles = full_candles[0:3]  # Only first 3 candles
        
        # Precompute on sliced window
        precompute_zone_freshness([zone], sliced_candles)
        
        # Touch should be at idx 2 (relative to sliced window)
        assert zone.first_touch_idx == 2
        assert zone.ever_touched is True
        
        # Freshness should be relative to sliced window
        assert is_zone_fresh_at_idx(zone, 0) == True
        assert is_zone_fresh_at_idx(zone, 1) == True
        assert is_zone_fresh_at_idx(zone, 2) == False
    
    def test_recompute_after_window_change(self):
        """If window changes, precompute should be re-run"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
        )
        
        # Window 1: Touch at idx 2
        window1 = [
            {'low': 90, 'high': 110},   # idx 0
            {'low': 110, 'high': 115},  # idx 1
            {'low': 96, 'high': 102},   # idx 2: Touch
        ]
        
        precompute_zone_freshness([zone], window1)
        assert zone.first_touch_idx == 2
        assert zone.ever_touched is True
        
        # Window 2: Extended, touch at idx 4
        window2 = [
            {'low': 90, 'high': 110},   # idx 0
            {'low': 110, 'high': 115},  # idx 1
            {'low': 110, 'high': 115},  # idx 2: NO touch (different candle)
            {'low': 110, 'high': 115},  # idx 3
            {'low': 96, 'high': 102},   # idx 4: Touch
        ]
        
        # Re-run precompute with new window
        precompute_zone_freshness([zone], window2)
        assert zone.first_touch_idx == 4  # Different result!
        assert zone.ever_touched is True
        
        # Verify freshness with new window
        assert is_zone_fresh_at_idx(zone, 2) == True  # Now fresh
        assert is_zone_fresh_at_idx(zone, 4) == False  # Touch moved
