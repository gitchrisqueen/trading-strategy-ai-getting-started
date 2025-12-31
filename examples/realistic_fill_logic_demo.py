"""Example demonstrating realistic fill logic and trading costs

This script shows how to:
1. Create a trade plan with limit order
2. Simulate order fills with TTL
3. Calculate PnL with fees and slippage
"""

import sys
import os

# Add repository root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    OrderState,
    build_trade_plan,
    check_limit_order_fill,
    calculate_pnl_with_costs,
    calculate_trading_costs,
)


def simulate_trade_with_fill_logic():
    """Simulate a complete trade lifecycle with realistic fill logic"""
    
    print("=" * 80)
    print("Supply & Demand V1: Realistic Fill Logic and Trading Costs Example")
    print("=" * 80)
    
    # Create a demand zone (long setup)
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=2,
        legout_end_idx=5,
        base_len=3,
        legout_len=3,
        freshness_touches=0,
        legout_return=0.08,  # 8% return on leg-out
        is_fresh=True
    )
    
    print(f"\n1. Zone Created:")
    print(f"   Type: {zone.zone_type.value.upper()}")
    print(f"   Proximal (Entry): ${zone.proximal:.2f}")
    print(f"   Distal (Stop Reference): ${zone.distal:.2f}")
    print(f"   Fresh: {zone.is_fresh}")
    
    # Set up parameters with realistic costs
    params = SupplyDemandParameters(
        stop_buffer_pct=0.001,  # 0.1% buffer on stop
        fees_bps=10.0,          # 0.1% trading fees
        slippage_bps=5.0,       # 0.05% slippage
        ttl_bars=10,            # Order expires after 10 bars
        min_reward_risk=3.0     # Minimum 3:1 R:R
    )
    
    print(f"\n2. Strategy Parameters:")
    print(f"   Trading Fees: {params.fees_bps} bps (0.{int(params.fees_bps/10)}%)")
    print(f"   Slippage: {params.slippage_bps} bps (0.0{int(params.slippage_bps)}%)")
    print(f"   TTL: {params.ttl_bars} bars")
    print(f"   Min R:R: {params.min_reward_risk}:1")
    
    # Build trade plan
    account_size = 10000.0
    current_price = 102.0
    
    trade_plan = build_trade_plan(
        zone=zone,
        current_price=current_price,
        account_size=account_size,
        parameters=params,
        opposing_zone=None,
        score=8.0
    )
    
    if trade_plan is None:
        print("\n✗ Trade plan rejected (insufficient R:R)")
        return
    
    print(f"\n3. Trade Plan Created:")
    print(f"   Entry Price (Limit): ${trade_plan.entry_price:.2f}")
    print(f"   Stop Loss: ${trade_plan.stop_loss:.2f}")
    print(f"   Take Profit: ${trade_plan.take_profit:.2f}")
    print(f"   Position Size: {trade_plan.position_size:.2f} units")
    print(f"   Risk Amount: ${trade_plan.risk_amount:.2f}")
    print(f"   Reward Amount: ${trade_plan.reward_amount:.2f}")
    print(f"   R:R Ratio: {trade_plan.r_multiple:.2f}:1")
    print(f"   Order State: {trade_plan.order_state.value.upper()}")
    
    # Simulate price action over multiple bars
    print(f"\n4. Simulating Price Action:")
    
    # Order placed at bar 0
    trade_plan.placed_at_idx = 0
    
    # Generate synthetic candles
    candles = [
        # Bars 0-4: Price stays above limit
        {'open': 105, 'high': 107, 'low': 103, 'close': 106},  # Bar 0
        {'open': 106, 'high': 108, 'low': 104, 'close': 107},  # Bar 1
        {'open': 107, 'high': 109, 'low': 105, 'close': 108},  # Bar 2
        {'open': 108, 'high': 110, 'low': 106, 'close': 109},  # Bar 3
        {'open': 109, 'high': 111, 'low': 107, 'close': 110},  # Bar 4
        # Bar 5: Price touches limit - ORDER FILLS
        {'open': 107, 'high': 108, 'low': 100, 'close': 105},  # Bar 5
        # Bars 6-8: Price moves in profit
        {'open': 105, 'high': 108, 'low': 104, 'close': 107},  # Bar 6
        {'open': 107, 'high': 112, 'low': 106, 'close': 110},  # Bar 7
        {'open': 110, 'high': 115, 'low': 109, 'close': 115},  # Bar 8 - Hit target
    ]
    
    filled = False
    fill_bar = None
    
    for bar_idx, candle in enumerate(candles):
        print(f"   Bar {bar_idx}: O=${candle['open']:.2f} H=${candle['high']:.2f} "
              f"L=${candle['low']:.2f} C=${candle['close']:.2f}", end="")
        
        if trade_plan.order_state == OrderState.PENDING:
            result = check_limit_order_fill(trade_plan, candles, bar_idx, params)
            if result:
                filled = True
                fill_bar = bar_idx
                print(f" ✓ FILLED at ${trade_plan.actual_entry_price:.4f}")
            elif trade_plan.order_state == OrderState.CANCELLED:
                print(f" ✗ CANCELLED (TTL expired)")
                break
            else:
                print(f" - Order pending ({bar_idx - trade_plan.placed_at_idx + 1}/{params.ttl_bars})")
        else:
            print("")
    
    if not filled:
        print("\n✗ Order never filled")
        return
    
    print(f"\n5. Order Fill Details:")
    print(f"   Filled at Bar: {fill_bar}")
    print(f"   Limit Price: ${trade_plan.entry_price:.2f}")
    print(f"   Actual Entry Price: ${trade_plan.actual_entry_price:.4f}")
    print(f"   Slippage: ${trade_plan.actual_entry_price - trade_plan.entry_price:.4f}")
    print(f"   Entry Cost (Fees + Slippage): ${trade_plan.entry_cost:.2f}")
    
    # Calculate PnL at different exit prices
    print(f"\n6. PnL Analysis at Different Exit Points:")
    
    exit_scenarios = [
        ("Stop Loss", trade_plan.stop_loss),
        ("Breakeven", trade_plan.entry_price),
        ("1R Target", trade_plan.entry_price + (trade_plan.entry_price - trade_plan.stop_loss)),
        ("2R Target", trade_plan.entry_price + 2 * (trade_plan.entry_price - trade_plan.stop_loss)),
        ("3R Target (TP)", trade_plan.take_profit),
    ]
    
    for scenario_name, exit_price in exit_scenarios:
        pnl = calculate_pnl_with_costs(trade_plan, exit_price, params)
        pnl_pct = (pnl / account_size) * 100
        
        # Calculate R multiple
        risk = abs(trade_plan.entry_price - trade_plan.stop_loss)
        profit = exit_price - trade_plan.actual_entry_price if zone.zone_type == ZoneType.DEMAND else trade_plan.actual_entry_price - exit_price
        r_achieved = profit / risk if risk > 0 else 0
        
        status = "✓" if pnl > 0 else "✗" if pnl < 0 else "="
        print(f"   {status} {scenario_name:15} @ ${exit_price:6.2f}: "
              f"PnL = ${pnl:7.2f} ({pnl_pct:+6.2f}%) | {r_achieved:+5.2f}R")
    
    print(f"\n7. Key Metrics Summary:")
    
    # Calculate final PnL at take profit
    final_pnl = calculate_pnl_with_costs(trade_plan, trade_plan.take_profit, params)
    final_pnl_pct = (final_pnl / account_size) * 100
    
    # Calculate what PnL would be without costs
    gross_pnl = (trade_plan.take_profit - trade_plan.entry_price) * trade_plan.position_size
    total_costs = trade_plan.entry_cost + calculate_trading_costs(
        trade_plan.take_profit,
        trade_plan.position_size,
        params.fees_bps,
        params.slippage_bps
    )
    
    print(f"   Gross PnL (without costs): ${gross_pnl:.2f}")
    print(f"   Total Costs: ${total_costs:.2f}")
    print(f"   Net PnL (with costs): ${final_pnl:.2f}")
    print(f"   Cost Impact: {(total_costs/gross_pnl)*100:.2f}% of gross profit")
    print(f"   Account Return: {final_pnl_pct:+.2f}%")
    print(f"   Win/Loss Amount: {final_pnl/abs(trade_plan.risk_amount):.2f}x risk")
    
    print("\n" + "=" * 80)
    print("✓ Example complete!")
    print("=" * 80)


def demonstrate_ttl_cancellation():
    """Demonstrate TTL order cancellation"""
    
    print("\n\n")
    print("=" * 80)
    print("Demonstrating TTL Order Cancellation")
    print("=" * 80)
    
    zone = Zone(
        zone_type=ZoneType.DEMAND,
        proximal=100.0,
        distal=95.0,
        created_at=0,
        base_start_idx=0,
        base_end_idx=2,
        legout_end_idx=5,
        base_len=3,
        legout_len=3,
        is_fresh=True
    )
    
    params = SupplyDemandParameters(
        stop_buffer_pct=0.0,
        fees_bps=10.0,
        slippage_bps=5.0,
        ttl_bars=5  # Short TTL for demonstration
    )
    
    trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
    trade_plan.placed_at_idx = 0
    
    print(f"\nOrder placed with {params.ttl_bars}-bar TTL")
    print(f"Limit price: ${trade_plan.entry_price:.2f}\n")
    
    # Generate candles that never touch the limit
    candles = [
        {'open': 105, 'high': 107, 'low': 103, 'close': 106}
        for _ in range(10)
    ]
    
    for bar_idx in range(6):
        candle = candles[bar_idx]
        print(f"Bar {bar_idx}: Low=${candle['low']:.2f} (above limit)", end="")
        
        result = check_limit_order_fill(trade_plan, candles, bar_idx, params)
        
        if trade_plan.order_state == OrderState.CANCELLED:
            print(f" ✗ CANCELLED (TTL expired)")
            break
        elif result:
            print(f" ✓ FILLED")
            break
        else:
            bars_remaining = params.ttl_bars - (bar_idx - trade_plan.placed_at_idx)
            print(f" - Pending ({bars_remaining} bars remaining)")
    
    print(f"\nFinal order state: {trade_plan.order_state.value.upper()}")
    print("=" * 80)


if __name__ == "__main__":
    # Run the main example
    simulate_trade_with_fill_logic()
    
    # Run the TTL cancellation demo
    demonstrate_ttl_cancellation()
