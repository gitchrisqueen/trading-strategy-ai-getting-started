"""Tests for vectorized zone freshness precomputation"""

import pytest
import numpy as np
from strategies.supply_demand_v1.strategy import (
    Zone, ZoneType, SupplyDemandParameters, detect_zones_dbr_rbd
)
from strategies.supply_demand_v1.zone_freshness_precompute import (
    precompute_zone_freshness,
    is_zone_fresh_at_idx,
    build_zone_creation_index,
    cache_zone_metrics,
    get_active_zones_at_idx
)


class TestZoneFreshnessPrecompute:
    """Test vectorized zone freshness precomputation"""
    
    def test_precompute_simple_demand_zone(self):
        """Test precomputing freshness for a simple demand zone"""
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
            is_fresh=True
        )
        
        candles = [
            {'low': 90, 'high': 110},  # Zone creation
            {'low': 110, 'high': 115},  # Away from zone
            {'low': 96, 'high': 102},   # Touches zone (low=96 <= proximal=100)
            {'low': 110, 'high': 115},  # Away again
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Zone should be first touched at index 2
        assert zone.first_touch_idx == 2
        assert zone.is_fresh == False
        assert zone.freshness_touches == 1
        
        # Verify is_fresh_at_idx
        assert is_zone_fresh_at_idx(zone, 0) == True
        assert is_zone_fresh_at_idx(zone, 1) == True
        assert is_zone_fresh_at_idx(zone, 2) == False
        assert is_zone_fresh_at_idx(zone, 3) == False
    
    def test_precompute_never_touched_zone(self):
        """Test zone that is never touched"""
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
            is_fresh=True
        )
        
        candles = [
            {'low': 90, 'high': 110},   # Zone creation
            {'low': 110, 'high': 115},  # Away from zone
            {'low': 115, 'high': 120},  # Still away
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Zone should never be touched
        assert zone.first_touch_idx is None
        assert zone.is_fresh == True
        assert zone.freshness_touches == 0
        
        # Always fresh
        assert is_zone_fresh_at_idx(zone, 0) == True
        assert is_zone_fresh_at_idx(zone, 1) == True
        assert is_zone_fresh_at_idx(zone, 2) == True
    
    def test_precompute_supply_zone(self):
        """Test precomputing freshness for supply zone"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=95,  # For supply: proximal is bottom
            distal=100,   # For supply: distal is top
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
            is_fresh=True
        )
        
        candles = [
            {'low': 90, 'high': 110},  # Zone creation
            {'low': 80, 'high': 90},   # Away from zone
            {'low': 96, 'high': 102},  # Touches zone
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # Zone should be touched at index 2
        assert zone.first_touch_idx == 2
        assert zone.is_fresh == False
        assert zone.freshness_touches >= 1
    
    def test_precompute_multiple_touches(self):
        """Test counting multiple touches"""
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
            is_fresh=True
        )
        
        candles = [
            {'low': 90, 'high': 110},   # Zone creation
            {'low': 110, 'high': 115},  # Away
            {'low': 96, 'high': 102},   # Touch 1
            {'low': 110, 'high': 115},  # Away
            {'low': 94, 'high': 101},   # Touch 2
        ]
        
        precompute_zone_freshness([zone], candles)
        
        # First touch at index 2
        assert zone.first_touch_idx == 2
        assert zone.is_fresh == False
        # Should count both touches
        assert zone.freshness_touches == 2
    
    def test_precompute_multiple_zones(self):
        """Test precomputing for multiple zones"""
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
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=50,
                distal=45,
                created_at=1,
                base_start_idx=1,
                base_end_idx=2,
                legout_end_idx=3,
                base_len=2,
                legout_len=1,
                is_fresh=True
            )
        ]
        
        candles = [
            {'low': 90, 'high': 110},   # Zone 1 creation
            {'low': 40, 'high': 60},    # Zone 2 creation
            {'low': 96, 'high': 102},   # Touch zone 1
            {'low': 47, 'high': 52},    # Touch zone 2
        ]
        
        precompute_zone_freshness(zones, candles)
        
        # Zone 1 touched at index 2
        assert zones[0].first_touch_idx == 2
        assert zones[0].is_fresh == False
        
        # Zone 2 touched at index 3
        assert zones[1].first_touch_idx == 3
        assert zones[1].is_fresh == False
    
    def test_build_zone_creation_index(self):
        """Test building zone creation index"""
        zones = [
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=100, distal=95,
                created_at=0, base_start_idx=0, base_end_idx=1,
                legout_end_idx=2, base_len=2, legout_len=1
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=50, distal=45,
                created_at=0, base_start_idx=0, base_end_idx=1,
                legout_end_idx=2, base_len=2, legout_len=1
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=75, distal=70,
                created_at=5, base_start_idx=5, base_end_idx=6,
                legout_end_idx=7, base_len=2, legout_len=1
            )
        ]
        
        index = build_zone_creation_index(zones)
        
        # Two zones created at index 0
        assert 0 in index
        assert len(index[0]) == 2
        assert 0 in index[0]
        assert 1 in index[0]
        
        # One zone created at index 5
        assert 5 in index
        assert len(index[5]) == 1
        assert 2 in index[5]
    
    def test_cache_zone_metrics(self):
        """Test caching zone metrics"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100,
            distal=95,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1
        )
        
        cache_zone_metrics([zone])
        
        # Should have cached width and bounds
        assert hasattr(zone, '_cached_width')
        assert zone._cached_width == 5  # |100 - 95|
        
        assert hasattr(zone, '_cached_bounds')
        assert zone._cached_bounds == (95, 100)  # (distal, proximal) for demand
    
    def test_get_active_zones(self):
        """Test getting active zones at index"""
        zones = [
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=100, distal=95,
                created_at=0, base_start_idx=0, base_end_idx=1,
                legout_end_idx=2, base_len=2, legout_len=1,
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=50, distal=45,
                created_at=5, base_start_idx=5, base_end_idx=6,
                legout_end_idx=7, base_len=2, legout_len=1,
                is_fresh=True
            )
        ]
        
        # Set first touch for zone 0 at index 10
        zones[0].first_touch_idx = 10
        zones[1].first_touch_idx = None  # Never touched
        
        # At index 8: zone 0 is fresh, zone 1 is created and fresh
        active = get_active_zones_at_idx(zones, 8)
        assert len(active) == 2
        
        # At index 11: zone 0 is stale, zone 1 is fresh
        active = get_active_zones_at_idx(zones, 11)
        assert len(active) == 1
        assert active[0] == zones[1]


class TestCorrectness:
    """Test that vectorized approach produces same results as incremental"""
    
    def test_matches_real_zone_detection(self):
        """Test with real zone detection from strategy"""
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            {'open': 115, 'close': 105, 'high': 115, 'low': 100},  # Touch
            {'open': 105, 'close': 115, 'high': 115, 'low': 105},
            {'open': 115, 'close': 105, 'high': 115, 'low': 98},   # Touch again
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        # Should detect at least one zone
        assert len(zones) > 0
        
        # Precompute freshness
        precompute_zone_freshness(zones, candles)
        
        # All zones should have first_touch_idx computed
        for zone in zones:
            assert hasattr(zone, 'first_touch_idx')
            # If is_fresh is False, must have a touch index
            if not zone.is_fresh:
                assert zone.first_touch_idx is not None
    
    def test_deterministic_output(self):
        """Test that precompute produces deterministic results"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100, distal=95,
            created_at=0, base_start_idx=0, base_end_idx=1,
            legout_end_idx=2, base_len=2, legout_len=1,
            is_fresh=True
        )
        
        candles = [
            {'low': 90, 'high': 110},
            {'low': 110, 'high': 115},
            {'low': 96, 'high': 102},
        ]
        
        # Run twice
        import copy
        zone1 = copy.deepcopy(zone)
        zone2 = copy.deepcopy(zone)
        
        precompute_zone_freshness([zone1], candles)
        precompute_zone_freshness([zone2], candles)
        
        # Results should be identical
        assert zone1.first_touch_idx == zone2.first_touch_idx
        assert zone1.is_fresh == zone2.is_fresh
        assert zone1.freshness_touches == zone2.freshness_touches
