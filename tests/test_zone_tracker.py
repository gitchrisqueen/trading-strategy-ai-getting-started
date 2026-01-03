"""Tests for the optimized zone freshness tracker with spatial indexing"""

import pytest
from strategies.supply_demand_v1.strategy import Zone, ZoneType, SupplyDemandParameters, detect_zones_dbr_rbd
from strategies.supply_demand_v1.zone_tracker import ZoneFreshnessTracker, update_zone_freshness_optimized


class TestZoneFreshnessTracker:
    """Test the spatial indexing optimization for zone freshness tracking"""
    
    def test_tracker_initialization(self):
        """Test that tracker initializes correctly"""
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
            )
        ]
        
        tracker = ZoneFreshnessTracker(zones, bucket_size=10.0)
        
        assert tracker.zones == zones
        assert tracker.bucket_size == 10.0
        assert len(tracker.price_buckets) > 0
    
    def test_get_overlapping_zones_simple(self):
        """Test finding zones that overlap with a candle"""
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
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=2,
                legout_len=1,
                is_fresh=True
            )
        ]
        
        tracker = ZoneFreshnessTracker(zones, bucket_size=10.0)
        
        # Candle that overlaps first zone
        candle = {'low': 98, 'high': 102}
        overlapping = tracker.get_overlapping_zones(candle)
        assert len(overlapping) == 1
        assert overlapping[0] == 0
        
        # Candle that overlaps second zone
        candle = {'low': 47, 'high': 52}
        overlapping = tracker.get_overlapping_zones(candle)
        assert len(overlapping) == 1
        assert overlapping[0] == 1
        
        # Candle that doesn't overlap any zone
        candle = {'low': 120, 'high': 125}
        overlapping = tracker.get_overlapping_zones(candle)
        assert len(overlapping) == 0
    
    def test_get_overlapping_zones_multiple(self):
        """Test finding multiple overlapping zones"""
        zones = [
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=105,
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
                proximal=102,
                distal=98,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=2,
                legout_len=1,
                is_fresh=True
            )
        ]
        
        tracker = ZoneFreshnessTracker(zones, bucket_size=5.0)
        
        # Candle that overlaps both zones
        candle = {'low': 96, 'high': 104}
        overlapping = tracker.get_overlapping_zones(candle)
        assert len(overlapping) == 2
    
    def test_update_zone_freshness_marks_stale(self):
        """Test that zones are correctly marked as stale when touched"""
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
                is_fresh=True,
                last_checked_idx=-1
            )
        ]
        
        candles = [
            {'low': 90, 'high': 110},  # Zone creation
            {'low': 110, 'high': 115},  # Away from zone
            {'low': 96, 'high': 102},   # Touches zone
        ]
        
        tracker = ZoneFreshnessTracker(zones, bucket_size=10.0)
        
        # Update at candle 1 (away from zone)
        tracker.update_zone_freshness(candles, 1)
        assert zones[0].is_fresh == True  # DEPRECATED field check (still fresh)
        
        # Update at candle 2 (touches zone)
        tracker.update_zone_freshness(candles, 2)
        assert zones[0].is_fresh == False  # DEPRECATED field check (now touched)
        assert zones[0].freshness_touches == 1
    
    def test_optimized_function_integration(self):
        """Test the wrapper function works correctly"""
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            {'open': 115, 'close': 105, 'high': 115, 'low': 98},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) > 0, "Should detect at least one zone"
        
        # Use optimized function to update freshness
        tracker = None
        for idx in range(len(candles)):
            tracker = update_zone_freshness_optimized(zones, candles, idx, tracker)
        
        # Check that freshness was updated correctly
        # Zone should be touched by candle 4 (low=98 enters zone)
        assert not all(z.is_fresh for z in zones), "At least one zone should be stale"
    
    def test_supply_zone_freshness(self):
        """Test freshness tracking for supply zones"""
        zones = [
            Zone(
                zone_type=ZoneType.SUPPLY,
                proximal=95,  # For supply: proximal is bottom
                distal=100,   # For supply: distal is top
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=2,
                legout_len=1,
                is_fresh=True,
                last_checked_idx=-1
            )
        ]
        
        candles = [
            {'low': 90, 'high': 110},  # Zone creation
            {'low': 80, 'high': 90},   # Away from zone
            {'low': 96, 'high': 102},  # Touches zone
        ]
        
        tracker = ZoneFreshnessTracker(zones, bucket_size=10.0)
        
        # Update through all candles
        for idx in range(len(candles)):
            tracker.update_zone_freshness(candles, idx)
        
        # Zone should be stale after candle 2 (DEPRECATED field check)
        assert zones[0].is_fresh == False
        assert zones[0].freshness_touches >= 1
    
    def test_performance_with_many_zones(self):
        """Test that performance is reasonable with many zones"""
        import time
        
        # Create 1000 zones at different price levels
        zones = []
        for i in range(1000):
            zones.append(Zone(
                zone_type=ZoneType.DEMAND,
                proximal=100 + i * 10,
                distal=95 + i * 10,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=2,
                legout_len=1,
                is_fresh=True,
                last_checked_idx=-1
            ))
        
        # Create 100 candles
        candles = []
        for i in range(100):
            candles.append({
                'low': 100 + i,
                'high': 110 + i
            })
        
        # Time the tracker creation and updates
        start = time.time()
        tracker = ZoneFreshnessTracker(zones, bucket_size=50.0)
        
        for idx in range(len(candles)):
            tracker.update_zone_freshness(candles, idx)
        
        elapsed = time.time() - start
        
        # Should complete in under 1 second
        assert elapsed < 1.0, f"Performance test took {elapsed:.3f}s, expected < 1.0s"
        
        # Verify some zones were updated
        updated_zones = [z for z in zones if z.last_checked_idx >= 0]
        assert len(updated_zones) > 0, "Some zones should have been updated"


class TestOptimizationCorrectness:
    """Test that the optimized version produces same results as naive version"""
    
    def test_same_results_as_naive_approach(self):
        """Verify optimized tracker gives same results as checking all zones"""
        from strategies.supply_demand_v1.strategy import is_zone_fresh
        
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            {'open': 115, 'close': 105, 'high': 115, 'low': 100},
            {'open': 105, 'close': 115, 'high': 115, 'low': 105},
            {'open': 115, 'close': 105, 'high': 115, 'low': 98},
        ]
        
        params = SupplyDemandParameters()
        
        # Get zones and make two copies
        zones_naive = detect_zones_dbr_rbd(candles, params)
        zones_optimized = detect_zones_dbr_rbd(candles, params)
        
        # Update using naive approach (original is_zone_fresh)
        for idx in range(len(candles)):
            for zone in zones_naive:
                if zone.created_at < idx:
                    is_zone_fresh(zone, candles, idx)
        
        # Update using optimized approach
        tracker = None
        for idx in range(len(candles)):
            tracker = update_zone_freshness_optimized(zones_optimized, candles, idx, tracker)
        
        # Compare results
        assert len(zones_naive) == len(zones_optimized)
        
        # Verify is_fresh (DEPRECATED field) matches between naive and optimized
        for i in range(len(zones_naive)):
            assert zones_naive[i].is_fresh == zones_optimized[i].is_fresh, \
                f"Zone {i}: naive={zones_naive[i].is_fresh}, optimized={zones_optimized[i].is_fresh}"
            assert zones_naive[i].freshness_touches == zones_optimized[i].freshness_touches, \
                f"Zone {i}: naive touches={zones_naive[i].freshness_touches}, optimized touches={zones_optimized[i].freshness_touches}"
