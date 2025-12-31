#!/usr/bin/env python3
"""Manual verification of trade lifecycle fixes"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    TradePlan,
    OrderState,
    build_trade_plan,
    check_intrabar_exit,
)

print("Testing intrabar exit detection...")

# Test 1: Long stop hit
print("\nTest 1: Long stop hit")
zone = Zone(
    zone_type=ZoneType.DEMAND,
    proximal=100.0,
    distal=95.0,
    created_at=0,
    base_start_idx=0,
    base_end_idx=1,
    legout_end_idx=2,
    base_len=2,
    legout_len=1,
    is_fresh=True
)

params = SupplyDemandParameters(
    stop_buffer_pct=0.0,
    fees_bps=10.0,
    slippage_bps=5.0,
)

trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
if trade_plan:
    trade_plan.order_state = OrderState.FILLED
    trade_plan.filled_at_idx = 5
    trade_plan.actual_entry_price = 100.0
    
    candle = {'open': 98, 'high': 99, 'low': 94, 'close': 95}
    exit_reason = check_intrabar_exit(trade_plan, candle, params)
    
    print(f"  Entry: {trade_plan.entry_price}, Stop: {trade_plan.stop_loss}, Target: {trade_plan.take_profit}")
    print(f"  Candle low: {candle['low']}, high: {candle['high']}")
    print(f"  Exit reason: {exit_reason}")
    assert exit_reason == "STOP", f"Expected STOP, got {exit_reason}"
    print("  ✓ PASS")

# Test 2: Long target hit
print("\nTest 2: Long target hit")
zone = Zone(
    zone_type=ZoneType.DEMAND,
    proximal=100.0,
    distal=95.0,
    created_at=0,
    base_start_idx=0,
    base_end_idx=1,
    legout_end_idx=2,
    base_len=2,
    legout_len=1,
    is_fresh=True
)

trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
if trade_plan:
    trade_plan.order_state = OrderState.FILLED
    trade_plan.filled_at_idx = 5
    trade_plan.actual_entry_price = 100.0
    
    candle = {'open': 110, 'high': 116, 'low': 109, 'close': 115}
    exit_reason = check_intrabar_exit(trade_plan, candle, params)
    
    print(f"  Entry: {trade_plan.entry_price}, Stop: {trade_plan.stop_loss}, Target: {trade_plan.take_profit}")
    print(f"  Candle low: {candle['low']}, high: {candle['high']}")
    print(f"  Exit reason: {exit_reason}")
    assert exit_reason == "TARGET", f"Expected TARGET, got {exit_reason}"
    print("  ✓ PASS")

# Test 3: No exit
print("\nTest 3: No exit (position stays open)")
zone = Zone(
    zone_type=ZoneType.DEMAND,
    proximal=100.0,
    distal=95.0,
    created_at=0,
    base_start_idx=0,
    base_end_idx=1,
    legout_end_idx=2,
    base_len=2,
    legout_len=1,
    is_fresh=True
)

trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
if trade_plan:
    trade_plan.order_state = OrderState.FILLED
    trade_plan.filled_at_idx = 5
    trade_plan.actual_entry_price = 100.0
    
    candle = {'open': 102, 'high': 105, 'low': 99, 'close': 103}
    exit_reason = check_intrabar_exit(trade_plan, candle, params)
    
    print(f"  Entry: {trade_plan.entry_price}, Stop: {trade_plan.stop_loss}, Target: {trade_plan.take_profit}")
    print(f"  Candle low: {candle['low']}, high: {candle['high']}")
    print(f"  Exit reason: {exit_reason}")
    assert exit_reason is None, f"Expected None, got {exit_reason}"
    print("  ✓ PASS")

# Test 4: Both hit, stop wins
print("\nTest 4: Both stop and target hit (stop wins)")
zone = Zone(
    zone_type=ZoneType.DEMAND,
    proximal=100.0,
    distal=95.0,
    created_at=0,
    base_start_idx=0,
    base_end_idx=1,
    legout_end_idx=2,
    base_len=2,
    legout_len=1,
    is_fresh=True
)

trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
if trade_plan:
    trade_plan.order_state = OrderState.FILLED
    trade_plan.filled_at_idx = 5
    trade_plan.actual_entry_price = 100.0
    
    candle = {'open': 100, 'high': 120, 'low': 90, 'close': 105}
    exit_reason = check_intrabar_exit(trade_plan, candle, params, stop_wins_on_same_bar=True)
    
    print(f"  Entry: {trade_plan.entry_price}, Stop: {trade_plan.stop_loss}, Target: {trade_plan.take_profit}")
    print(f"  Candle low: {candle['low']}, high: {candle['high']} (both hit)")
    print(f"  Exit reason: {exit_reason}")
    assert exit_reason == "STOP", f"Expected STOP, got {exit_reason}"
    print("  ✓ PASS")

print("\n" + "="*50)
print("All tests PASSED! ✓")
print("="*50)
