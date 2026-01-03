"""Unit tests for supply and demand zone detection

Tests cover:
- Boring vs exciting candle classification
- DBR (Drop-Base-Rally) zone detection
- RBD (Rally-Base-Drop) zone detection
- Proximal and distal line calculation
- Freshness tracking (fresh -> not fresh after touch)
"""

import pytest
from strategies.supply_demand_v1.strategy import (
    identify_boring_candles,
    identify_exciting_candles,
    calculate_body_and_range,
    detect_zones_dbr_rbd,
    compute_zone_lines_proximal_distal,
    is_zone_fresh,
    SupplyDemandParameters,
    ZoneType,
)


class TestCandleClassification:
    """Test candle classification (boring vs exciting)"""
    
    def test_boring_candle_small_body(self):
        """Test that candles with small bodies are classified as boring"""
        # Create a candle with body = 0.3 * range (30% of range)
        candles = [
            {'open': 100, 'close': 101, 'high': 103, 'low': 99}  # body=1, range=4, ratio=0.25
        ]
        boring = identify_boring_candles(candles, body_ratio=0.50)
        assert boring[0] is True, "Candle with body=25% of range should be boring"
    
    def test_boring_candle_exact_threshold(self):
        """Test candle exactly at threshold is boring"""
        candles = [
            {'open': 100, 'close': 102, 'high': 104, 'low': 100}  # body=2, range=4, ratio=0.50
        ]
        boring = identify_boring_candles(candles, body_ratio=0.50)
        assert boring[0] is True, "Candle with body=50% of range should be boring"
    
    def test_exciting_candle_large_body(self):
        """Test that candles with large bodies are classified as exciting"""
        candles = [
            {'open': 100, 'close': 103, 'high': 104, 'low': 100}  # body=3, range=4, ratio=0.75
        ]
        exciting = identify_exciting_candles(candles, body_ratio=0.50)
        assert exciting[0] is True, "Candle with body=75% of range should be exciting"
    
    def test_exciting_candle_just_above_threshold(self):
        """Test candle just above threshold is exciting"""
        candles = [
            {'open': 100, 'close': 102.1, 'high': 104, 'low': 100}  # body=2.1, range=4, ratio=0.525
        ]
        exciting = identify_exciting_candles(candles, body_ratio=0.50)
        assert exciting[0] is True, "Candle with body=52.5% of range should be exciting"
    
    def test_doji_candle(self):
        """Test that doji (no range) is handled gracefully"""
        candles = [
            {'open': 100, 'close': 100, 'high': 100, 'low': 100}  # body=0, range=0
        ]
        boring = identify_boring_candles(candles, body_ratio=0.50)
        exciting = identify_exciting_candles(candles, body_ratio=0.50)
        assert boring[0] is True, "Doji should be classified as boring"
        assert exciting[0] is False, "Doji should not be classified as exciting"
    
    def test_body_and_range_calculation(self):
        """Test body and range calculation helper"""
        candle = {'open': 100, 'close': 105, 'high': 107, 'low': 98}
        body, range_val = calculate_body_and_range(candle)
        assert body == 5, "Body should be |105-100| = 5"
        assert range_val == 9, "Range should be 107-98 = 9"
    
    def test_body_bearish_candle(self):
        """Test body calculation for bearish candle"""
        candle = {'open': 105, 'close': 100, 'high': 107, 'low': 98}
        body, range_val = calculate_body_and_range(candle)
        assert body == 5, "Body should be |100-105| = 5 (absolute value)"
        assert range_val == 9, "Range should be 107-98 = 9"


class TestDBRDetection:
    """Test Drop-Base-Rally (demand) zone detection"""
    
    def test_simple_dbr_detection(self):
        """Test detection of basic DBR pattern"""
        # Pattern: exciting drop -> boring base -> exciting rally
        candles = [
            # Leg-in: exciting drop
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},  # idx 0: body=10, range=10 (100% - exciting)
            # Base: boring consolidation
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},   # idx 1: body=1, range=3 (33% - boring)
            {'open': 101, 'close': 100, 'high': 102, 'low': 99},   # idx 2: body=1, range=3 (33% - boring)
            # Leg-out: exciting rally
            {'open': 100, 'close': 110, 'high': 110, 'low': 100},  # idx 3: body=10, range=10 (100% - exciting)
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect exactly one DBR zone"
        zone = zones[0]
        assert zone.zone_type == ZoneType.DEMAND, "Should be a demand zone"
        assert zone.base_len == 2, "Base should have 2 candles"
        assert zone.legout_len >= 1, "Leg-out should have at least 1 candle"
    
    def test_dbr_proximal_distal_body_mode(self):
        """Test proximal and distal calculation for DBR (body mode)"""
        # DBR pattern with clear base
        candles = [
            # Leg-in: drop
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},   # idx 0: low=95
            # Base: boring candles
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},   # idx 1: body top=101
            {'open': 101, 'close': 102, 'high': 103, 'low': 100},  # idx 2: body top=102
            # Leg-out: rally
            {'open': 102, 'close': 115, 'high': 115, 'low': 102},  # idx 3: rally
        ]
        
        params = SupplyDemandParameters(proximal_mode="body")
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Proximal should be highest body in base (102)
        assert zone.proximal == 102, f"Proximal should be 102 (highest body in base), got {zone.proximal}"
        # Distal should be lowest low across full pattern (95)
        assert zone.distal == 95, f"Distal should be 95 (lowest low), got {zone.distal}"
    
    def test_dbr_multiple_base_candles(self):
        """Test DBR detection with longer base"""
        candles = [
            # Leg-in: exciting drop
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},
            # Base: 3 boring candles
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 100.5, 'high': 102, 'low': 99},
            {'open': 100.5, 'close': 101, 'high': 102, 'low': 99},
            # Leg-out: exciting rally
            {'open': 101, 'close': 112, 'high': 112, 'low': 101},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        assert zones[0].base_len == 3, "Base should have 3 candles"
        assert zones[0].zone_type == ZoneType.DEMAND


class TestRBDDetection:
    """Test Rally-Base-Drop (supply) zone detection"""
    
    def test_simple_rbd_detection(self):
        """Test detection of basic RBD pattern"""
        # Pattern: exciting rally -> boring base -> exciting drop
        candles = [
            # Leg-in: exciting rally
            {'open': 100, 'close': 110, 'high': 110, 'low': 100},  # idx 0: body=10, range=10 (100% - exciting)
            # Base: boring consolidation
            {'open': 110, 'close': 109, 'high': 111, 'low': 108},  # idx 1: body=1, range=3 (33% - boring)
            {'open': 109, 'close': 110, 'high': 111, 'low': 108},  # idx 2: body=1, range=3 (33% - boring)
            # Leg-out: exciting drop
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},  # idx 3: body=10, range=10 (100% - exciting)
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect exactly one RBD zone"
        zone = zones[0]
        assert zone.zone_type == ZoneType.SUPPLY, "Should be a supply zone"
        assert zone.base_len == 2, "Base should have 2 candles"
        assert zone.legout_len >= 1, "Leg-out should have at least 1 candle"
    
    def test_rbd_proximal_distal_body_mode(self):
        """Test proximal and distal calculation for RBD (body mode)"""
        # RBD pattern with clear base
        candles = [
            # Leg-in: rally
            {'open': 100, 'close': 110, 'high': 115, 'low': 100},  # idx 0: high=115
            # Base: boring candles
            {'open': 110, 'close': 109, 'high': 111, 'low': 108},  # idx 1: body bottom=109
            {'open': 109, 'close': 108, 'high': 110, 'low': 107},  # idx 2: body bottom=108
            # Leg-out: drop
            {'open': 108, 'close': 95, 'high': 108, 'low': 95},    # idx 3: drop
        ]
        
        params = SupplyDemandParameters(proximal_mode="body")
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Proximal should be lowest body in base (108)
        assert zone.proximal == 108, f"Proximal should be 108 (lowest body in base), got {zone.proximal}"
        # Distal should be highest high across full pattern (115)
        assert zone.distal == 115, f"Distal should be 115 (highest high), got {zone.distal}"
    
    def test_rbd_with_wick_mode(self):
        """Test RBD with wick mode for proximal"""
        candles = [
            # Leg-in: rally
            {'open': 100, 'close': 110, 'high': 115, 'low': 100},
            # Base: boring candles
            {'open': 110, 'close': 109, 'high': 111, 'low': 105},  # low=105 (wick)
            {'open': 109, 'close': 108, 'high': 110, 'low': 106},  # low=106 (wick)
            # Leg-out: drop
            {'open': 108, 'close': 95, 'high': 108, 'low': 95},
        ]
        
        params = SupplyDemandParameters(proximal_mode="wick")
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Proximal should be lowest low in base (105) in wick mode
        assert zone.proximal == 105, f"Proximal should be 105 (lowest low in base), got {zone.proximal}"


class TestFreshnessTracking:
    """Test zone freshness tracking"""
    
    def test_fresh_zone_no_touch(self):
        """Test that zone remains fresh when price doesn't touch it"""
        # Create a demand zone
        candles = [
            # Zone creation: DBR pattern
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            # Candles after zone creation (price stays above zone)
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            {'open': 115, 'close': 120, 'high': 120, 'low': 115},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Check freshness at current candle
        current_idx = len(candles) - 1
        is_fresh = is_zone_fresh(zone, candles, current_idx)
        
        assert is_fresh is True, "Zone should remain fresh when not touched"
        assert zone.freshness_touches == 0, "Touch count should be 0"
    
    def test_zone_becomes_not_fresh_after_touch(self):
        """Test that zone becomes not fresh after price touches it"""
        # Create a demand zone
        candles = [
            # Zone creation: DBR pattern
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},   # low=95
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},   # body: 100-101
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            # Price moves away
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            # Price returns to zone (touches it)
            {'open': 115, 'close': 105, 'high': 115, 'low': 100},  # low=100 overlaps zone
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Check freshness after touch
        current_idx = len(candles) - 1
        is_fresh = is_zone_fresh(zone, candles, current_idx)
        
        assert is_fresh is False, "Zone should not be fresh after being touched"
        assert zone.freshness_touches >= 1, f"Touch count should be at least 1, got {zone.freshness_touches}"
    
    def test_zone_touch_count(self):
        """Test that multiple touches are counted correctly"""
        # Create a demand zone
        candles = [
            # Zone creation: DBR pattern (zone roughly 95-102)
            {'open': 110, 'close': 100, 'high': 110, 'low': 95},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            # Price moves away and touches zone twice
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},  # away
            {'open': 115, 'close': 105, 'high': 115, 'low': 100},  # touch 1
            {'open': 105, 'close': 115, 'high': 115, 'low': 105},  # away
            {'open': 115, 'close': 105, 'high': 115, 'low': 98},   # touch 2
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        
        # Check freshness
        current_idx = len(candles) - 1
        is_zone_fresh(zone, candles, current_idx)
        
        # Note: is_fresh is DEPRECATED field (final state), use is_zone_fresh_at_idx() for time-relative checks
        assert zone.is_fresh is False, "Zone should not be fresh"
        # Touch count could be 2-4 depending on how many candles overlap
        assert zone.freshness_touches >= 2, f"Should have at least 2 touches, got {zone.freshness_touches}"
    
    def test_supply_zone_freshness(self):
        """Test freshness tracking for supply zone"""
        # Create a supply zone
        candles = [
            # Zone creation: RBD pattern (zone roughly 108-115)
            {'open': 100, 'close': 110, 'high': 115, 'low': 100},
            {'open': 110, 'close': 109, 'high': 111, 'low': 108},
            {'open': 109, 'close': 100, 'high': 109, 'low': 100},
            # Price moves away (stays below zone)
            {'open': 100, 'close': 95, 'high': 100, 'low': 95},
            # Price returns to zone
            {'open': 95, 'close': 110, 'high': 112, 'low': 95},  # high=112 overlaps zone
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1, "Should detect one zone"
        zone = zones[0]
        assert zone.zone_type == ZoneType.SUPPLY
        
        # Check freshness
        current_idx = len(candles) - 1
        is_fresh = is_zone_fresh(zone, candles, current_idx)
        
        assert is_fresh is False, "Supply zone should not be fresh after being touched"
        assert zone.freshness_touches >= 1, "Touch count should be at least 1"


class TestZoneAttributes:
    """Test that zones have correct attributes"""
    
    def test_zone_has_required_attributes(self):
        """Test that detected zones have all required attributes"""
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1
        zone = zones[0]
        
        # Check all required attributes exist
        assert hasattr(zone, 'zone_type')
        assert hasattr(zone, 'proximal')
        assert hasattr(zone, 'distal')
        assert hasattr(zone, 'created_at')
        assert hasattr(zone, 'base_start_idx')
        assert hasattr(zone, 'base_end_idx')
        assert hasattr(zone, 'legout_end_idx')
        assert hasattr(zone, 'base_len')
        assert hasattr(zone, 'legout_len')
        assert hasattr(zone, 'freshness_touches')
        assert hasattr(zone, 'legout_return')
        assert hasattr(zone, 'is_fresh')
        
        # Check types
        assert isinstance(zone.zone_type, ZoneType)
        assert isinstance(zone.proximal, (int, float))
        assert isinstance(zone.distal, (int, float))
        assert isinstance(zone.created_at, int)
        assert isinstance(zone.base_len, int)
        assert isinstance(zone.legout_len, int)
        assert isinstance(zone.freshness_touches, int)
        # Note: is_fresh is DEPRECATED field (kept for backward compatibility)
        assert isinstance(zone.is_fresh, bool)
    
    def test_zone_created_at_index(self):
        """Test that created_at is set to legout_end_idx"""
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},  # idx 0
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},   # idx 1
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},  # idx 2
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1
        zone = zones[0]
        
        assert zone.created_at == zone.legout_end_idx
        assert zone.created_at == 2, "Zone should be created at index 2 (last candle)"
    
    def test_zone_strength_metrics(self):
        """Test that strength metrics are calculated"""
        candles = [
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 115, 'high': 115, 'low': 101},  # Large leg-out
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 1
        zone = zones[0]
        
        # legout_return should be calculated
        assert zone.legout_return > 0, "Leg-out return should be positive"
        # For this example, leg-out goes from ~101 to 115, so return ~13.9%
        assert zone.legout_return > 0.10, f"Leg-out return should be > 10%, got {zone.legout_return}"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_no_zones_in_short_data(self):
        """Test that no zones are detected in insufficient data"""
        candles = [
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 0, "Should not detect zones with insufficient candles"
    
    def test_no_zones_all_boring(self):
        """Test that no zones are detected when all candles are boring"""
        candles = [
            {'open': 100, 'close': 100.5, 'high': 102, 'low': 99},
            {'open': 100.5, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 100.5, 'high': 102, 'low': 99},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 0, "Should not detect zones without exciting candles"
    
    def test_no_zones_all_exciting(self):
        """Test that no zones are detected when all candles are exciting"""
        candles = [
            {'open': 100, 'close': 110, 'high': 110, 'low': 100},
            {'open': 110, 'close': 120, 'high': 120, 'low': 110},
            {'open': 120, 'close': 130, 'high': 130, 'low': 120},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        assert len(zones) == 0, "Should not detect zones without boring base candles"
    
    def test_multiple_zones_in_sequence(self):
        """Test detection of multiple zones in sequence"""
        candles = [
            # First DBR zone
            {'open': 110, 'close': 100, 'high': 110, 'low': 100},
            {'open': 100, 'close': 101, 'high': 102, 'low': 99},
            {'open': 101, 'close': 110, 'high': 110, 'low': 101},
            # Some gap
            {'open': 110, 'close': 115, 'high': 115, 'low': 110},
            # Second RBD zone
            {'open': 115, 'close': 125, 'high': 125, 'low': 115},
            {'open': 125, 'close': 124, 'high': 126, 'low': 123},
            {'open': 124, 'close': 115, 'high': 124, 'low': 115},
        ]
        
        params = SupplyDemandParameters()
        zones = detect_zones_dbr_rbd(candles, params)
        
        # May detect 1 or 2 zones depending on pattern recognition
        assert len(zones) >= 1, "Should detect at least one zone"
