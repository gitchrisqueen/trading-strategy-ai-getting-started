"""Vectorized zone freshness precomputation using NumPy

This module implements O(Z + C) freshness computation by precomputing
when each zone is first touched, eliminating the need for per-candle freshness checks.

Key optimization:
- Instead of checking each zone against every candle: O(Z × C)
- Precompute first touch index for all zones once: O(Z + C)
- Then O(1) lookup during backtest loop
"""

import numpy as np
from typing import List, Dict, Any, Optional
from strategies.supply_demand_v1.strategy import Zone, ZoneType


def precompute_zone_freshness(
    zones: List[Zone],
    candles: List[Dict[str, Any]]
) -> None:
    """Precompute first touch index for all zones using vectorized operations
    
    This function computes when each zone is first touched by price action
    and stores it in the zone object. This eliminates the need to check
    freshness during the backtest loop.
    
    IMPORTANT: This sets FINAL state fields (ever_touched, is_fresh for backward compat)
    NOT time-relative freshness. Use is_zone_fresh_at_idx(zone, idx) for time-relative checks.
    
    Args:
        zones: List of all zones detected
        candles: List of all candle dictionaries
    
    Side effects:
        Updates zone.first_touch_idx (index of first touch, or None if never touched)
        Updates zone.ever_touched (final state: True if touched at any point)
        Updates zone.freshness_touches (total touch count)
        Updates zone.is_fresh (DEPRECATED: set to !ever_touched for backward compat)
    
    Complexity: O(Z + C) where Z = zones, C = candles
    """
    if not candles or not zones:
        return
    
    # Convert candle data to numpy arrays for vectorized operations
    lows = np.array([c['low'] for c in candles], dtype=np.float64)
    highs = np.array([c['high'] for c in candles], dtype=np.float64)
    num_candles = len(candles)
    
    # Process each zone
    for zone in zones:
        # Define zone bounds based on type
        if zone.zone_type == ZoneType.DEMAND:
            # For demand zones: proximal is top, distal is bottom
            zone_top = zone.proximal
            zone_bottom = zone.distal
        else:  # SUPPLY
            # For supply zones: proximal is bottom, distal is top
            zone_top = zone.distal
            zone_bottom = zone.proximal
        
        # Only check candles after zone creation
        if zone.created_at + 1 >= num_candles:
            # Zone created at or after last candle - never touched
            zone.first_touch_idx = None
            zone.ever_touched = False
            zone.is_fresh = True  # DEPRECATED field, kept for backward compat
            zone.freshness_touches = 0
            zone.last_checked_idx = num_candles - 1
            continue
        
        # Create mask for candles after zone creation
        start_idx = zone.created_at + 1
        
        # Vectorized overlap check: candle overlaps zone if:
        # candle's low <= zone_top AND candle's high >= zone_bottom
        overlaps = (lows[start_idx:] <= zone_top) & (highs[start_idx:] >= zone_bottom)
        
        # Find first touch using argmax (first True in boolean array)
        if overlaps.any():
            # Find first touch relative to start_idx
            first_touch_relative = np.argmax(overlaps)
            first_touch_idx = start_idx + first_touch_relative
            
            # Count total touches
            touch_count = np.sum(overlaps)
            
            # Update zone with final state
            zone.first_touch_idx = first_touch_idx
            zone.ever_touched = True
            zone.is_fresh = False  # DEPRECATED field, kept for backward compat
            zone.freshness_touches = int(touch_count)
            zone.last_checked_idx = num_candles - 1
        else:
            # Zone never touched
            zone.first_touch_idx = None
            zone.ever_touched = False
            zone.is_fresh = True  # DEPRECATED field, kept for backward compat
            zone.freshness_touches = 0
            zone.last_checked_idx = num_candles - 1


def is_zone_fresh_at_idx(zone: Zone, idx: int) -> bool:
    """Check if zone is fresh at a given candle index - O(1) lookup
    
    Args:
        zone: Zone to check (must have first_touch_idx computed)
        idx: Candle index to check
    
    Returns:
        True if zone is fresh at this index, False otherwise
    """
    # If first_touch_idx is None, zone is never touched (always fresh)
    if zone.first_touch_idx is None:
        return True
    
    # Zone is fresh if we're before the first touch
    return idx < zone.first_touch_idx


def get_active_zones_at_idx(
    zones: List[Zone],
    idx: int,
    created_by_idx: Optional[Dict[int, List[int]]] = None
) -> List[Zone]:
    """Get zones that are active (created but not stale) at given index
    
    Args:
        zones: List of all zones
        idx: Current candle index
        created_by_idx: Optional dict mapping creation index to zone indices
    
    Returns:
        List of zones that are active at this index
    """
    if created_by_idx is not None:
        # Use index if provided (faster)
        active = []
        for create_idx in range(max(0, idx - 100), idx + 1):  # Look back reasonable window
            if create_idx in created_by_idx:
                for zone_idx in created_by_idx[create_idx]:
                    zone = zones[zone_idx]
                    if zone.created_at <= idx and is_zone_fresh_at_idx(zone, idx):
                        active.append(zone)
        return active
    else:
        # Linear scan (slower but simpler)
        return [
            z for z in zones
            if z.created_at <= idx and is_zone_fresh_at_idx(z, idx)
        ]


def build_zone_creation_index(zones: List[Zone]) -> Dict[int, List[int]]:
    """Build index mapping candle index to zones created at that index
    
    Args:
        zones: List of all zones
    
    Returns:
        Dict mapping creation index to list of zone indices
    """
    created_by_idx = {}
    for zone_idx, zone in enumerate(zones):
        if zone.created_at not in created_by_idx:
            created_by_idx[zone.created_at] = []
        created_by_idx[zone.created_at].append(zone_idx)
    return created_by_idx


def cache_zone_metrics(zones: List[Zone]) -> None:
    """Cache expensive zone metrics that don't change
    
    Args:
        zones: List of zones to cache metrics for
    
    Side effects:
        Adds cached attributes to zone objects
    """
    for zone in zones:
        # Cache zone width
        if not hasattr(zone, '_cached_width'):
            zone._cached_width = abs(zone.proximal - zone.distal)
        
        # Cache zone bounds
        if not hasattr(zone, '_cached_bounds'):
            if zone.zone_type == ZoneType.DEMAND:
                zone._cached_bounds = (zone.distal, zone.proximal)  # (bottom, top)
            else:  # SUPPLY
                zone._cached_bounds = (zone.proximal, zone.distal)  # (bottom, top)
