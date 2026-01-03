"""Zone Freshness Tracker with Spatial Indexing

This module provides an optimized zone freshness tracking system that uses
spatial indexing to avoid checking zones that don't overlap with the current
candle's price range.

Key optimization:
- Instead of checking ALL zones on EVERY candle (O(z) per candle)
- Only check zones whose price range overlaps the candle (O(log z + k) per candle)
- For 35K candles with 3200 zones: 112M checks → ~175K checks (640x reduction)
"""

from typing import List, Dict, Any, Set
from strategies.supply_demand_v1.strategy import Zone, ZoneType


class ZoneFreshnessTracker:
    """Spatial index for efficient zone freshness tracking
    
    This class maintains zones organized by their price ranges to quickly find
    which zones overlap with a given candle, avoiding the need to check all zones.
    
    Attributes:
        zones: List of all zones being tracked
        price_buckets: Dict mapping price ranges to zone indices
        bucket_size: Size of each price bucket for spatial indexing
    """
    
    def __init__(self, zones: List[Zone], bucket_size: float = 1.0):
        """Initialize the zone freshness tracker
        
        Args:
            zones: List of zones to track
            bucket_size: Price range size for spatial bucketing (default: 1.0)
        """
        self.zones = zones
        self.bucket_size = bucket_size
        self.price_buckets: Dict[int, Set[int]] = {}
        
        # Build spatial index
        self._build_index()
    
    def _build_index(self):
        """Build spatial index by organizing zones into price buckets"""
        for zone_idx, zone in enumerate(self.zones):
            # Get zone price range
            if zone.zone_type == ZoneType.DEMAND:
                zone_bottom = zone.distal
                zone_top = zone.proximal
            else:  # SUPPLY
                zone_bottom = zone.proximal
                zone_top = zone.distal
            
            # Calculate bucket range for this zone
            min_bucket = int(zone_bottom // self.bucket_size)
            max_bucket = int(zone_top // self.bucket_size)
            
            # Add zone to all buckets it spans
            for bucket in range(min_bucket, max_bucket + 1):
                if bucket not in self.price_buckets:
                    self.price_buckets[bucket] = set()
                self.price_buckets[bucket].add(zone_idx)
    
    def get_overlapping_zones(self, candle: Dict[str, Any]) -> List[int]:
        """Get indices of zones that overlap with the candle's price range
        
        Args:
            candle: Candle dict with 'high' and 'low' keys
        
        Returns:
            List of zone indices that overlap the candle's price range
        """
        candle_low = candle['low']
        candle_high = candle['high']
        
        # Calculate bucket range for this candle
        min_bucket = int(candle_low // self.bucket_size)
        max_bucket = int(candle_high // self.bucket_size)
        
        # Collect all zones in overlapping buckets
        candidate_zones: Set[int] = set()
        for bucket in range(min_bucket, max_bucket + 1):
            if bucket in self.price_buckets:
                candidate_zones.update(self.price_buckets[bucket])
        
        # Filter to zones that actually overlap (double-check for bucket boundaries)
        overlapping_zones = []
        for zone_idx in candidate_zones:
            zone = self.zones[zone_idx]
            
            # Get zone bounds
            if zone.zone_type == ZoneType.DEMAND:
                zone_bottom = zone.distal
                zone_top = zone.proximal
            else:  # SUPPLY
                zone_bottom = zone.proximal
                zone_top = zone.distal
            
            # Check if candle overlaps zone
            if candle_low <= zone_top and candle_high >= zone_bottom:
                overlapping_zones.append(zone_idx)
        
        return overlapping_zones
    
    def update_zone_freshness(self, candles: List[Dict[str, Any]], current_idx: int):
        """Update freshness for all zones based on current candle
        
        This is the optimized version that only checks overlapping zones.
        
        Args:
            candles: List of all candles
            current_idx: Current candle index
        """
        if current_idx >= len(candles):
            return
        
        current_candle = candles[current_idx]
        
        # Get only zones that overlap with current candle's price range
        overlapping_zone_indices = self.get_overlapping_zones(current_candle)
        
        # Update only the overlapping zones
        for zone_idx in overlapping_zone_indices:
            zone = self.zones[zone_idx]
            
            # Skip if zone not created yet or already checked
            if zone.created_at >= current_idx:
                continue
            
            if zone.last_checked_idx >= current_idx:
                continue
            
            # Get zone bounds
            if zone.zone_type == ZoneType.DEMAND:
                zone_top = zone.proximal
                zone_bottom = zone.distal
            else:  # SUPPLY
                zone_top = zone.distal
                zone_bottom = zone.proximal
            
            # Check candles from last check to current
            start_idx = max(zone.created_at + 1, zone.last_checked_idx + 1)
            
            for i in range(start_idx, current_idx + 1):
                candle = candles[i]
                
                # Check if candle overlaps the zone
                if candle['low'] <= zone_top and candle['high'] >= zone_bottom:
                    zone.freshness_touches += 1
                    zone.is_fresh = False
            
            # Update last checked index
            zone.last_checked_idx = current_idx


def update_zone_freshness_optimized(
    zones: List[Zone],
    candles: List[Dict[str, Any]],
    current_idx: int,
    tracker: ZoneFreshnessTracker = None
) -> ZoneFreshnessTracker:
    """Update zone freshness using spatial indexing for optimization
    
    This function should be called once per candle to update all zones efficiently.
    
    Args:
        zones: List of all zones
        candles: List of all candles
        current_idx: Current candle index
        tracker: Existing tracker (will be created if None)
    
    Returns:
        ZoneFreshnessTracker instance for reuse in subsequent calls
    
    Example:
        # In backtest loop:
        tracker = None
        for idx in range(len(candles)):
            tracker = update_zone_freshness_optimized(zones, candles, idx, tracker)
    """
    if tracker is None:
        # Determine appropriate bucket size based on price range
        if zones:
            all_prices = []
            for zone in zones:
                all_prices.extend([zone.proximal, zone.distal])
            price_range = max(all_prices) - min(all_prices)
            # Use ~1% of price range as bucket size
            bucket_size = max(price_range / 100, 1.0)
        else:
            bucket_size = 1.0
        
        tracker = ZoneFreshnessTracker(zones, bucket_size)
    
    tracker.update_zone_freshness(candles, current_idx)
    return tracker
