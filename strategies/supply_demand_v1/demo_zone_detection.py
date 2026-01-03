"""Demonstration of Supply and Demand Zone Detection

This script demonstrates the zone detection functionality with a simple example.
"""

from strategy import (
    detect_zones_dbr_rbd,
    is_zone_fresh,
    SupplyDemandParameters,
    ZoneType,
)


def print_zone_info(zone, idx):
    """Print formatted zone information"""
    print(f"\n{'='*60}")
    print(f"Zone #{idx + 1}: {zone.zone_type.value.upper()}")
    print(f"{'='*60}")
    print(f"Created at index: {zone.created_at}")
    print(f"Proximal line:    ${zone.proximal:.2f}")
    print(f"Distal line:      ${zone.distal:.2f}")
    print(f"Base length:      {zone.base_len} candle(s)")
    print(f"Leg-out length:   {zone.legout_len} candle(s)")
    print(f"Leg-out return:   {zone.legout_return*100:.2f}%")
    print(f"Freshness:        {'FRESH' if zone.is_fresh else 'NOT FRESH'} ({zone.freshness_touches} touches)")
    print(f"                  (Note: This is FINAL state - use is_zone_fresh_at_idx() for time-relative checks)")


def demo_dbr_zone():
    """Demonstrate DBR (Drop-Base-Rally) demand zone detection"""
    print("\n" + "="*60)
    print("DEMO 1: Drop-Base-Rally (DBR) - DEMAND ZONE")
    print("="*60)
    
    candles = [
        # Exciting drop (leg-in)
        {'open': 110, 'close': 100, 'high': 110, 'low': 95},
        # Boring base (consolidation)
        {'open': 100, 'close': 101, 'high': 102, 'low': 99},
        {'open': 101, 'close': 100, 'high': 102, 'low': 99},
        # Exciting rally (leg-out)
        {'open': 100, 'close': 115, 'high': 115, 'low': 100},
        # Price continues higher (away from zone)
        {'open': 115, 'close': 120, 'high': 120, 'low': 115},
    ]
    
    print("\nCandle data:")
    for i, c in enumerate(candles):
        body = abs(c['close'] - c['open'])
        range_val = c['high'] - c['low']
        ratio = (body / range_val * 100) if range_val > 0 else 0
        candle_type = "EXCITING" if ratio > 50 else "BORING"
        print(f"  {i}: O=${c['open']:6.2f} H=${c['high']:6.2f} L=${c['low']:6.2f} C=${c['close']:6.2f} "
              f"body={body:5.2f} range={range_val:5.2f} ({ratio:5.1f}%) {candle_type}")
    
    params = SupplyDemandParameters()
    zones = detect_zones_dbr_rbd(candles, params)
    
    for i, zone in enumerate(zones):
        print_zone_info(zone, i)
        
        # Check freshness
        current_idx = len(candles) - 1
        is_zone_fresh(zone, candles, current_idx)
        
        print(f"\nInterpretation:")
        print(f"  • This is a DEMAND zone where buyers stepped in")
        print(f"  • Entry: Place buy limit near proximal line (${zone.proximal:.2f})")
        print(f"  • Stop: Place stop below distal line (${zone.distal:.2f})")
        print(f"  • The zone is {'FRESH - never tested' if zone.is_fresh else f'NOT FRESH - touched {zone.freshness_touches} times'}")


def demo_rbd_zone():
    """Demonstrate RBD (Rally-Base-Drop) supply zone detection"""
    print("\n" + "="*60)
    print("DEMO 2: Rally-Base-Drop (RBD) - SUPPLY ZONE")
    print("="*60)
    
    candles = [
        # Exciting rally (leg-in)
        {'open': 100, 'close': 110, 'high': 115, 'low': 100},
        # Boring base (consolidation)
        {'open': 110, 'close': 109, 'high': 111, 'low': 108},
        {'open': 109, 'close': 110, 'high': 111, 'low': 108},
        # Exciting drop (leg-out)
        {'open': 110, 'close': 95, 'high': 110, 'low': 95},
        # Price continues lower (away from zone)
        {'open': 95, 'close': 90, 'high': 95, 'low': 90},
        # Price returns and touches the zone
        {'open': 90, 'close': 105, 'high': 110, 'low': 90},
    ]
    
    print("\nCandle data:")
    for i, c in enumerate(candles):
        body = abs(c['close'] - c['open'])
        range_val = c['high'] - c['low']
        ratio = (body / range_val * 100) if range_val > 0 else 0
        candle_type = "EXCITING" if ratio > 50 else "BORING"
        print(f"  {i}: O=${c['open']:6.2f} H=${c['high']:6.2f} L=${c['low']:6.2f} C=${c['close']:6.2f} "
              f"body={body:5.2f} range={range_val:5.2f} ({ratio:5.1f}%) {candle_type}")
    
    params = SupplyDemandParameters()
    zones = detect_zones_dbr_rbd(candles, params)
    
    for i, zone in enumerate(zones):
        print_zone_info(zone, i)
        
        # Check freshness before and after touch
        print(f"\n  Checking freshness at index 4 (before touch):")
        is_zone_fresh(zone, candles, 4)
        print(f"    Fresh: {zone.is_fresh}, Touches: {zone.freshness_touches}")
        
        print(f"\n  Checking freshness at index 5 (after touch):")
        is_zone_fresh(zone, candles, 5)
        print(f"    Fresh: {zone.is_fresh}, Touches: {zone.freshness_touches}")
        
        print(f"\nInterpretation:")
        print(f"  • This is a SUPPLY zone where sellers stepped in")
        print(f"  • Entry: Place sell limit near proximal line (${zone.proximal:.2f})")
        print(f"  • Stop: Place stop above distal line (${zone.distal:.2f})")
        print(f"  • The zone was tested at candle 5, so it's NO LONGER FRESH")


def demo_proximal_modes():
    """Demonstrate different proximal line placement modes"""
    print("\n" + "="*60)
    print("DEMO 3: Proximal Line Placement - Body vs Wick Mode")
    print("="*60)
    
    candles = [
        {'open': 110, 'close': 100, 'high': 110, 'low': 95},
        {'open': 100, 'close': 101, 'high': 105, 'low': 99},  # Note: high wick to 105
        {'open': 101, 'close': 115, 'high': 115, 'low': 101},
    ]
    
    print("\nCandle data (note the base candle has a wick to 105):")
    for i, c in enumerate(candles):
        print(f"  {i}: O=${c['open']:6.2f} H=${c['high']:6.2f} L=${c['low']:6.2f} C=${c['close']:6.2f}")
    
    print("\n--- Body Mode (default) ---")
    params_body = SupplyDemandParameters(proximal_mode="body")
    zones_body = detect_zones_dbr_rbd(candles, params_body)
    if zones_body:
        zone = zones_body[0]
        print(f"Proximal: ${zone.proximal:.2f} (highest candle BODY in base)")
        print(f"Distal:   ${zone.distal:.2f} (lowest LOW across full structure)")
    
    print("\n--- Wick Mode (conservative) ---")
    params_wick = SupplyDemandParameters(proximal_mode="wick")
    zones_wick = detect_zones_dbr_rbd(candles, params_wick)
    if zones_wick:
        zone = zones_wick[0]
        print(f"Proximal: ${zone.proximal:.2f} (highest HIGH in base - includes wick)")
        print(f"Distal:   ${zone.distal:.2f} (lowest LOW across full structure)")
        
    print("\nInterpretation:")
    print("  • Body mode uses the candle body for proximal line (tighter entry)")
    print("  • Wick mode uses the full candle including wick (more conservative)")
    print("  • Wick mode gives more buffer but may have lower win rate")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Supply and Demand Zone Detection - Demo")
    print("="*60)
    
    demo_dbr_zone()
    demo_rbd_zone()
    demo_proximal_modes()
    
    print("\n" + "="*60)
    print("Demo Complete!")
    print("="*60)
    print("\nKey Takeaways:")
    print("  1. Boring candles have body <= 50% of range (consolidation)")
    print("  2. Exciting candles have body > 50% of range (momentum)")
    print("  3. DBR (Drop-Base-Rally) creates DEMAND zones for long entries")
    print("  4. RBD (Rally-Base-Drop) creates SUPPLY zones for short entries")
    print("  5. Fresh zones are untouched - higher probability setups")
    print("  6. Proximal line = entry reference, Distal line = stop reference")
    print()
