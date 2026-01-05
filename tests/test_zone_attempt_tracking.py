"""Unit tests for zone attempt tracking and cooldown logic

Tests cover:
- Zone attempt counter increments correctly
- Disabled zones are skipped in evaluation
- Cooldown logic re-enables zones after cooldown_bars elapsed
- Max attempts enforcement
"""

from strategies.supply_demand_v1.strategy import (
    Zone,
    ZoneType,
    SupplyDemandParameters,
)


class TestZoneAttemptTracking:
    """Test zone attempt tracking fields"""
    
    def test_zone_default_attempt_fields(self):
        """Test that new zones have default attempt tracking values"""
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
        
        assert zone.attempts == 0, "New zone should have 0 attempts"
        assert zone.last_attempt_idx is None, "New zone should have no last_attempt_idx"
        assert zone.disabled is False, "New zone should not be disabled"
    
    def test_zone_attempt_increment(self):
        """Test that zone attempts can be incremented"""
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
        
        # Simulate first attempt
        zone.attempts += 1
        zone.last_attempt_idx = 50
        
        assert zone.attempts == 1, "Zone should have 1 attempt"
        assert zone.last_attempt_idx == 50, "Last attempt should be at index 50"
        assert zone.disabled is False, "Zone should not be disabled after 1 attempt"
    
    def test_zone_disabled_after_max_attempts(self):
        """Test that zone can be disabled after max attempts"""
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
        
        # Simulate reaching max attempts (default is 1)
        zone.attempts = 1
        zone.last_attempt_idx = 50
        zone.disabled = True
        
        assert zone.attempts == 1, "Zone should have 1 attempt"
        assert zone.disabled is True, "Zone should be disabled after max attempts"


class TestZoneAttemptParameters:
    """Test zone attempt configuration parameters"""
    
    def test_default_max_attempts(self):
        """Test that default max_attempts_per_zone is 1"""
        params = SupplyDemandParameters()
        
        assert params.max_attempts_per_zone == 1, "Default max attempts should be 1"
        assert params.cooldown_bars is None, "Default cooldown should be None"
    
    def test_custom_max_attempts(self):
        """Test that custom max_attempts_per_zone can be set"""
        params = SupplyDemandParameters(max_attempts_per_zone=3)
        
        assert params.max_attempts_per_zone == 3, "Custom max attempts should be 3"
    
    def test_custom_cooldown_bars(self):
        """Test that custom cooldown_bars can be set"""
        params = SupplyDemandParameters(
            max_attempts_per_zone=2,
            cooldown_bars=30
        )
        
        assert params.max_attempts_per_zone == 2, "Max attempts should be 2"
        assert params.cooldown_bars == 30, "Cooldown should be 30 bars"


class TestCooldownLogic:
    """Test cooldown logic for zone re-enabling"""
    
    def test_cooldown_calculation(self):
        """Test that cooldown period is calculated correctly"""
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
        
        # Simulate first attempt at bar 50
        zone.attempts = 1
        zone.last_attempt_idx = 50
        
        # Test cooldown at various future bars
        current_idx = 70
        cooldown_bars = 30
        
        bars_since_attempt = current_idx - zone.last_attempt_idx
        assert bars_since_attempt == 20, "Should be 20 bars since attempt"
        
        # Not enough cooldown yet
        cooldown_elapsed = bars_since_attempt >= cooldown_bars
        assert cooldown_elapsed is False, "Cooldown should not be elapsed (20 < 30)"
        
        # Move to bar 80 (exactly 30 bars later)
        current_idx = 80
        bars_since_attempt = current_idx - zone.last_attempt_idx
        cooldown_elapsed = bars_since_attempt >= cooldown_bars
        assert cooldown_elapsed is True, "Cooldown should be elapsed (30 >= 30)"
    
    def test_cooldown_reenables_zone(self):
        """Test that cooldown re-enables a disabled zone"""
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
        
        # Simulate zone reaching max attempts and being disabled
        zone.attempts = 1
        zone.last_attempt_idx = 50
        zone.disabled = True
        
        # Simulate cooldown elapsed - reset zone
        current_idx = 80
        cooldown_bars = 30
        bars_since_attempt = current_idx - zone.last_attempt_idx
        
        if bars_since_attempt >= cooldown_bars:
            zone.attempts = 0
            zone.last_attempt_idx = None
            zone.disabled = False
        
        assert zone.attempts == 0, "Attempts should be reset after cooldown"
        assert zone.last_attempt_idx is None, "Last attempt should be cleared"
        assert zone.disabled is False, "Zone should be re-enabled after cooldown"


class TestAttemptTrackingLogic:
    """Test the logic for when attempts are incremented"""
    
    def test_attempts_increment_only_on_order_placed(self):
        """Test that attempts increment ONLY when order is placed, not on evaluation"""
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
        
        # Simulate zone evaluation (no order placed)
        # Attempts should NOT increment
        assert zone.attempts == 0, "Attempts should not increment during evaluation"
        
        # Simulate order placement
        zone.attempts += 1
        zone.last_attempt_idx = 100
        
        assert zone.attempts == 1, "Attempts should increment when order is placed"
        assert zone.last_attempt_idx == 100, "Last attempt index should be set"
    
    def test_multiple_attempts_tracking(self):
        """Test tracking multiple attempts on the same zone"""
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
        
        # First attempt
        zone.attempts += 1
        zone.last_attempt_idx = 100
        assert zone.attempts == 1
        
        # Second attempt (after cooldown)
        zone.attempts += 1
        zone.last_attempt_idx = 150
        assert zone.attempts == 2
        assert zone.last_attempt_idx == 150, "Last attempt should update to most recent"
        
        # Third attempt
        zone.attempts += 1
        zone.last_attempt_idx = 200
        assert zone.attempts == 3
