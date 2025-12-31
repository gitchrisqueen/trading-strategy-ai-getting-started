"""Unit tests for multi-timeframe analysis and trade gating

Tests cover:
- Curve classification (LOW, EQ, HIGH)
- Trend classification (UP, DOWN, SIDEWAYS)
- Trade gating based on curve + trend alignment
- EQ-specific gating rules
"""

import pytest
from strategies.supply_demand_v1.strategy import (
    find_nearest_fresh_supply_above,
    find_nearest_fresh_demand_below,
    classify_curve,
    classify_trend,
    should_allow_trade,
    curve_location,
    detect_pivot_highs_lows,
    SupplyDemandParameters,
    Zone,
    ZoneType,
    CurveLocation,
)


class TestCurveClassification:
    """Test curve location classification"""
    
    def test_classify_curve_low_position(self):
        """Test price in LOW position (bottom third)"""
        # Range: 100 to 130 = 30
        # Thirds: [100, 110) = LOW, [110, 120) = EQ, [120, 130] = HIGH
        demand_proximal = 100.0
        supply_proximal = 130.0
        
        # Price at 105 should be LOW
        result = classify_curve(105.0, supply_proximal, demand_proximal)
        assert result == "LOW", f"Expected LOW, got {result}"
    
    def test_classify_curve_equilibrium_position(self):
        """Test price in EQUILIBRIUM position (middle third)"""
        demand_proximal = 100.0
        supply_proximal = 130.0
        
        # Price at 115 should be EQ
        result = classify_curve(115.0, supply_proximal, demand_proximal)
        assert result == "EQ", f"Expected EQ, got {result}"
    
    def test_classify_curve_high_position(self):
        """Test price in HIGH position (top third)"""
        demand_proximal = 100.0
        supply_proximal = 130.0
        
        # Price at 125 should be HIGH
        result = classify_curve(125.0, supply_proximal, demand_proximal)
        assert result == "HIGH", f"Expected HIGH, got {result}"
    
    def test_classify_curve_boundaries(self):
        """Test curve classification at exact boundaries"""
        demand_proximal = 100.0
        supply_proximal = 130.0
        
        # Boundary at 110: should be EQ (>= 110)
        result = classify_curve(110.0, supply_proximal, demand_proximal)
        assert result == "EQ", f"Expected EQ at boundary 110, got {result}"
        
        # Boundary at 120: should be HIGH (>= 120)
        result = classify_curve(120.0, supply_proximal, demand_proximal)
        assert result == "HIGH", f"Expected HIGH at boundary 120, got {result}"
    
    def test_classify_curve_missing_zones(self):
        """Test curve classification when zones are missing"""
        # No zones: should default to EQ
        result = classify_curve(115.0, None, None)
        assert result == "EQ", "Should default to EQ when zones missing"


class TestTrendClassification:
    """Test trend direction classification using pivots"""
    
    def test_classify_trend_uptrend_hh_hl(self):
        """Test uptrend detection: Higher Highs and Higher Lows"""
        # Create synthetic candles with clear uptrend
        candles = []
        # Create a series of higher highs and higher lows
        prices = [(90, 95), (95, 100), (100, 105), (105, 110), (110, 115)]
        
        for i, (low, high) in enumerate(prices):
            # Add candles before pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
            # Add the pivot candle
            candles.append({'open': low, 'close': high, 'high': high, 'low': low})
            # Add candles after pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
        
        # Detect pivots
        pivot_highs, pivot_lows = detect_pivot_highs_lows(candles, lookback=2)
        
        # Classify trend
        trend = classify_trend(pivot_highs, pivot_lows, candles, pivots_to_consider=3)
        assert trend == "UP", f"Expected UP trend, got {trend}"
    
    def test_classify_trend_downtrend_lh_ll(self):
        """Test downtrend detection: Lower Highs and Lower Lows"""
        # Create synthetic candles with clear downtrend
        candles = []
        # Create a series of lower highs and lower lows
        prices = [(110, 115), (105, 110), (100, 105), (95, 100), (90, 95)]
        
        for i, (low, high) in enumerate(prices):
            # Add candles before pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
            # Add the pivot candle
            candles.append({'open': high, 'close': low, 'high': high, 'low': low})
            # Add candles after pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
        
        # Detect pivots
        pivot_highs, pivot_lows = detect_pivot_highs_lows(candles, lookback=2)
        
        # Classify trend
        trend = classify_trend(pivot_highs, pivot_lows, candles, pivots_to_consider=3)
        assert trend == "DOWN", f"Expected DOWN trend, got {trend}"
    
    def test_classify_trend_sideways_mixed(self):
        """Test sideways detection: Mixed highs and lows"""
        # Create synthetic candles with sideways movement
        candles = []
        # Create a series of equal highs and equal lows
        prices = [(95, 105), (94, 106), (95, 105), (96, 104), (95, 105)]
        
        for i, (low, high) in enumerate(prices):
            # Add candles before pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
            # Add the pivot candle
            candles.append({'open': low+3, 'close': high-3, 'high': high, 'low': low})
            # Add candles after pivot
            for _ in range(3):
                candles.append({'open': low+1, 'close': low+2, 'high': high-1, 'low': low+0.5})
        
        # Detect pivots
        pivot_highs, pivot_lows = detect_pivot_highs_lows(candles, lookback=2)
        
        # Classify trend
        trend = classify_trend(pivot_highs, pivot_lows, candles, pivots_to_consider=3)
        assert trend == "SIDEWAYS", f"Expected SIDEWAYS trend, got {trend}"
    
    def test_classify_trend_insufficient_pivots(self):
        """Test trend classification with insufficient pivots"""
        candles = [
            {'open': 100, 'close': 101, 'high': 102, 'low': 99}
        ]
        
        pivot_highs, pivot_lows = detect_pivot_highs_lows(candles, lookback=5)
        
        # Should default to SIDEWAYS with insufficient data
        trend = classify_trend(pivot_highs, pivot_lows, candles, pivots_to_consider=4)
        assert trend == "SIDEWAYS", "Should return SIDEWAYS with insufficient pivots"


class TestFindNearestZones:
    """Test finding nearest fresh zones"""
    
    def test_find_nearest_fresh_supply_above(self):
        """Test finding nearest fresh supply zone above price"""
        zones = [
            Zone(
                zone_type=ZoneType.SUPPLY,
                proximal=150.0,
                distal=155.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.SUPPLY,
                proximal=130.0,  # Closer
                distal=135.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.DEMAND,  # Wrong type
                proximal=140.0,
                distal=135.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
        ]
        
        result = find_nearest_fresh_supply_above(120.0, zones)
        assert result is not None
        assert result.proximal == 130.0, "Should find the nearest supply zone"
    
    def test_find_nearest_fresh_demand_below(self):
        """Test finding nearest fresh demand zone below price"""
        zones = [
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=90.0,
                distal=85.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.DEMAND,
                proximal=100.0,  # Closer
                distal=95.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
            Zone(
                zone_type=ZoneType.SUPPLY,  # Wrong type
                proximal=95.0,
                distal=100.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=True
            ),
        ]
        
        result = find_nearest_fresh_demand_below(110.0, zones)
        assert result is not None
        assert result.proximal == 100.0, "Should find the nearest demand zone"
    
    def test_find_zones_no_fresh_zones(self):
        """Test when no fresh zones are available"""
        zones = [
            Zone(
                zone_type=ZoneType.SUPPLY,
                proximal=130.0,
                distal=135.0,
                created_at=0,
                base_start_idx=0,
                base_end_idx=1,
                legout_end_idx=2,
                base_len=1,
                legout_len=1,
                is_fresh=False  # Not fresh
            ),
        ]
        
        result = find_nearest_fresh_supply_above(120.0, zones)
        assert result is None, "Should return None when no fresh zones found"


class TestTradeGating:
    """Test trade gating based on curve + trend"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.params = SupplyDemandParameters()
    
    def test_low_curve_allows_demand_long(self):
        """Test LOW curve allows demand LONG trades"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "LOW", "UP", 6.0, self.params)
        assert allowed is True, "Should allow demand LONG in LOW curve"
        assert score == 6.0, "Score should remain unchanged"
    
    def test_low_curve_blocks_supply_short(self):
        """Test LOW curve blocks supply SHORT trades"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "LOW", "DOWN", 6.0, self.params)
        assert allowed is False, "Should block supply SHORT in LOW curve"
    
    def test_high_curve_allows_supply_short(self):
        """Test HIGH curve allows supply SHORT trades"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "HIGH", "DOWN", 6.0, self.params)
        assert allowed is True, "Should allow supply SHORT in HIGH curve"
        assert score == 6.0, "Score should remain unchanged"
    
    def test_high_curve_blocks_demand_long(self):
        """Test HIGH curve blocks demand LONG trades"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "HIGH", "UP", 6.0, self.params)
        assert allowed is False, "Should block demand LONG in HIGH curve"
    
    def test_eq_with_aligned_trend_long(self):
        """Test EQ allows LONG with aligned UP trend"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "UP", 6.0, self.params)
        assert allowed is True, "Should allow demand LONG in EQ with UP trend"
        assert score == 7.0, f"Score should include EQ bonus (+1.0), got {score}"
    
    def test_eq_with_aligned_trend_short(self):
        """Test EQ allows SHORT with aligned DOWN trend"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "DOWN", 6.0, self.params)
        assert allowed is True, "Should allow supply SHORT in EQ with DOWN trend"
        assert score == 7.0, "Score should include EQ bonus (+1.0)"
    
    def test_eq_blocks_misaligned_trend_long(self):
        """Test EQ blocks LONG with misaligned trend"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "DOWN", 6.0, self.params)
        assert allowed is False, "Should block demand LONG in EQ with DOWN trend"
    
    def test_eq_blocks_misaligned_trend_short(self):
        """Test EQ blocks SHORT with misaligned trend"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "UP", 6.0, self.params)
        assert allowed is False, "Should block supply SHORT in EQ with UP trend"
    
    def test_eq_blocks_sideways_trend(self):
        """Test EQ blocks trades with SIDEWAYS trend"""
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "SIDEWAYS", 6.0, self.params)
        assert allowed is False, "Should block trades in EQ with SIDEWAYS trend"
    
    def test_eq_disabled_blocks_all(self):
        """Test EQ trades blocked when allow_eq_trades=False"""
        params = SupplyDemandParameters(allow_eq_trades=False)
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "UP", 6.0, params)
        assert allowed is False, "Should block all EQ trades when disabled"
    
    def test_eq_without_trend_requirement(self):
        """Test EQ allows trades without trend alignment requirement"""
        params = SupplyDemandParameters(eq_requires_trend_alignment=False)
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        # Should allow even with misaligned trend
        allowed, score = should_allow_trade(zone, "EQ", "DOWN", 6.0, params)
        assert allowed is True, "Should allow EQ trades without trend alignment when disabled"
        assert score == 7.0, "Score should still include EQ bonus"
    
    def test_eq_custom_bonus(self):
        """Test EQ applies custom score bonus"""
        params = SupplyDemandParameters(eq_min_setup_score_bonus=2.5)
        zone = Zone(
            zone_type=ZoneType.DEMAND,
            proximal=100.0,
            distal=95.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=1,
            legout_len=1,
            is_fresh=True
        )
        
        allowed, score = should_allow_trade(zone, "EQ", "UP", 6.0, params)
        assert allowed is True
        assert score == 8.5, f"Score should include custom EQ bonus (+2.5), got {score}"
