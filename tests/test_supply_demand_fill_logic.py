"""Unit tests for realistic fill logic and trading costs

Tests cover:
- Limit order fill logic (long and short)
- Order not filled when price never touches
- Order fills on touch
- TTL cancellation
- Trading costs (fees + slippage)
- PnL calculation with costs
"""

import pytest
from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    Zone,
    ZoneType,
    TradePlan,
    OrderState,
    build_trade_plan,
    check_limit_order_fill,
    calculate_trading_costs,
    calculate_pnl_with_costs,
)


class TestTradingCosts:
    """Test trading cost calculations"""
    
    def test_calculate_trading_costs_basic(self):
        """Test basic trading cost calculation"""
        price = 100.0
        position_size = 10.0
        fees_bps = 10.0  # 0.1%
        slippage_bps = 5.0  # 0.05%
        
        cost = calculate_trading_costs(price, position_size, fees_bps, slippage_bps)
        
        # Total bps = 15, cost = 100 * 10 * 15 / 10000 = 1.5
        expected = 1.5
        assert abs(cost - expected) < 0.01, f"Expected {expected}, got {cost}"
    
    def test_calculate_trading_costs_zero_fees(self):
        """Test with zero fees and slippage"""
        cost = calculate_trading_costs(100.0, 10.0, 0.0, 0.0)
        assert cost == 0.0, "Cost should be zero with no fees or slippage"
    
    def test_calculate_trading_costs_large_position(self):
        """Test cost scales with position size"""
        price = 50000.0  # BTC price
        position_size = 1.0
        fees_bps = 10.0
        slippage_bps = 5.0
        
        cost = calculate_trading_costs(price, position_size, fees_bps, slippage_bps)
        
        # Total bps = 15, cost = 50000 * 1 * 15 / 10000 = 75
        expected = 75.0
        assert abs(cost - expected) < 0.01, f"Expected {expected}, got {cost}"


class TestLimitOrderFillLong:
    """Test limit order fill logic for long positions (DEMAND zones)"""
    
    def test_long_fills_when_low_touches_limit(self):
        """Test that long order fills when candle's low touches limit price"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price touches the limit
        candles = [
            {'open': 102, 'high': 103, 'low': 100, 'close': 101},  # Low touches limit at 100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is True, "Order should be filled when low touches limit"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == 0
        assert trade_plan.actual_entry_price is not None
        # Entry price should be limit + slippage
        expected_entry = 100.0 + (100.0 * 5.0 / 10000.0)  # 100.05
        assert abs(trade_plan.actual_entry_price - expected_entry) < 0.01
        assert trade_plan.entry_cost > 0, "Entry cost should be positive"
    
    def test_long_not_filled_when_price_stays_above(self):
        """Test that long order is not filled when price stays above limit"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price never touches the limit
        candles = [
            {'open': 105, 'high': 107, 'low': 103, 'close': 106},  # Low at 103 > limit 100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is False, "Order should not be filled when price never touches"
        assert trade_plan.order_state == OrderState.PENDING
        assert trade_plan.filled_at_idx is None
        assert trade_plan.actual_entry_price is None
    
    def test_long_fills_exactly_at_limit(self):
        """Test that long order fills when low exactly equals limit"""
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
        
        params = SupplyDemandParameters(stop_buffer_pct=0.0, ttl_bars=10)
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where low exactly equals limit
        candles = [
            {'open': 102, 'high': 103, 'low': 100.0, 'close': 101},  # Low = limit
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is True, "Order should fill when low exactly equals limit"
        assert trade_plan.order_state == OrderState.FILLED


class TestLimitOrderFillShort:
    """Test limit order fill logic for short positions (SUPPLY zones)"""
    
    def test_short_fills_when_high_touches_limit(self):
        """Test that short order fills when candle's high touches limit price"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 98.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price touches the limit
        candles = [
            {'open': 99, 'high': 100, 'low': 98, 'close': 99},  # High touches limit at 100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is True, "Order should be filled when high touches limit"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == 0
        assert trade_plan.actual_entry_price is not None
        # Entry price should be limit - slippage for short
        expected_entry = 100.0 - (100.0 * 5.0 / 10000.0)  # 99.95
        assert abs(trade_plan.actual_entry_price - expected_entry) < 0.01
        assert trade_plan.entry_cost > 0
    
    def test_short_not_filled_when_price_stays_below(self):
        """Test that short order is not filled when price stays below limit"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
            created_at=0,
            base_start_idx=0,
            base_end_idx=1,
            legout_end_idx=2,
            base_len=2,
            legout_len=1,
            is_fresh=True
        )
        
        params = SupplyDemandParameters(stop_buffer_pct=0.0, ttl_bars=10)
        
        trade_plan = build_trade_plan(
            zone, 98.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price never touches the limit
        candles = [
            {'open': 97, 'high': 98, 'low': 96, 'close': 97},  # High at 98 < limit 100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is False, "Order should not be filled when price never touches"
        assert trade_plan.order_state == OrderState.PENDING
        assert trade_plan.filled_at_idx is None


class TestTTLCancellation:
    """Test time-to-live order cancellation"""
    
    def test_order_cancelled_after_ttl_expires(self):
        """Test that order is cancelled when TTL expires"""
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
            ttl_bars=5  # 5 bar TTL
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price never touches for 5 bars
        candles = [
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 0
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 1
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 2
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 3
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 4
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 5 - should cancel
        ]
        
        # Check at bar 4 (not expired yet)
        filled = check_limit_order_fill(trade_plan, candles, 4, params)
        assert filled is False
        assert trade_plan.order_state == OrderState.PENDING
        
        # Check at bar 5 (expired)
        filled = check_limit_order_fill(trade_plan, candles, 5, params)
        assert filled is False
        assert trade_plan.order_state == OrderState.CANCELLED
    
    def test_order_fills_before_ttl_expires(self):
        """Test that order fills normally before TTL expires"""
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
            ttl_bars=5
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price touches at bar 3 (before TTL)
        candles = [
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 0
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 1
            {'open': 105, 'high': 106, 'low': 104, 'close': 105},  # idx 2
            {'open': 102, 'high': 103, 'low': 100, 'close': 101},  # idx 3 - touches
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 3, params)
        
        assert filled is True, "Order should fill before TTL expires"
        assert trade_plan.order_state == OrderState.FILLED
    
    def test_no_ttl_order_stays_pending(self):
        """Test that order with no TTL stays pending indefinitely"""
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
            ttl_bars=None  # No TTL
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Create candles where price never touches for many bars
        candles = [
            {'open': 105, 'high': 106, 'low': 104, 'close': 105}
            for _ in range(100)
        ]
        
        # Check at bar 99 - should still be pending
        filled = check_limit_order_fill(trade_plan, candles, 99, params)
        assert filled is False
        assert trade_plan.order_state == OrderState.PENDING


class TestPnLWithCosts:
    """Test PnL calculation with trading costs"""
    
    def test_profitable_long_with_costs(self):
        """Test profitable long position with trading costs"""
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
            fees_bps=10.0,  # 0.1%
            slippage_bps=5.0,  # 0.05%
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Fill the order
        candles = [{'open': 102, 'high': 103, 'low': 100, 'close': 101}]
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        assert filled is True
        
        # Calculate PnL at a profitable exit
        exit_price = 115.0  # 15% profit
        pnl = calculate_pnl_with_costs(trade_plan, exit_price, params)
        
        # Actual entry = 100.05 (with slippage)
        # Position size = 200 / 5 = 40 units (2% of 10000 = 200, risk per unit = 5)
        # Gross PnL = (115 - 100.05) * 40 = 598
        # Entry cost = 100.05 * 40 * 15 / 10000 = 6.003
        # Exit cost = 115 * 40 * 15 / 10000 = 6.9
        # Net PnL = 598 - 6.003 - 6.9 = 585.097
        
        expected_pnl = 585.097
        assert pnl > 0, "PnL should be positive"
        assert abs(pnl - expected_pnl) < 1.0, f"Expected ~{expected_pnl}, got {pnl}"
    
    def test_losing_long_with_costs(self):
        """Test losing long position with trading costs"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Fill the order
        candles = [{'open': 102, 'high': 103, 'low': 100, 'close': 101}]
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        assert filled is True
        
        # Calculate PnL at stop loss
        exit_price = 95.0  # Hit stop loss
        pnl = calculate_pnl_with_costs(trade_plan, exit_price, params)
        
        # Should be negative (loss + costs)
        assert pnl < 0, "PnL should be negative at stop loss"
        # Loss should be close to risk amount (200) plus costs
        assert pnl < -200, "Loss should be at least the risk amount"
    
    def test_costs_reduce_profit(self):
        """Test that costs reduce profit compared to gross PnL"""
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
        
        # Test with costs
        params_with_costs = SupplyDemandParameters(
            stop_buffer_pct=0.0,
            fees_bps=10.0,
            slippage_bps=5.0,
            ttl_bars=10
        )
        
        # Test without costs
        params_no_costs = SupplyDemandParameters(
            stop_buffer_pct=0.0,
            fees_bps=0.0,
            slippage_bps=0.0,
            ttl_bars=10
        )
        
        # Create two identical trade plans
        trade_plan_with_costs = build_trade_plan(
            zone, 102.0, 10000.0, params_with_costs, None
        )
        trade_plan_no_costs = build_trade_plan(
            zone, 102.0, 10000.0, params_no_costs, None
        )
        
        # Fill both orders
        candles = [{'open': 102, 'high': 103, 'low': 100, 'close': 101}]
        check_limit_order_fill(trade_plan_with_costs, candles, 0, params_with_costs)
        check_limit_order_fill(trade_plan_no_costs, candles, 0, params_no_costs)
        
        # Calculate PnL at same exit price
        exit_price = 110.0
        pnl_with_costs = calculate_pnl_with_costs(trade_plan_with_costs, exit_price, params_with_costs)
        pnl_no_costs = calculate_pnl_with_costs(trade_plan_no_costs, exit_price, params_no_costs)
        
        # PnL with costs should be lower
        assert pnl_with_costs < pnl_no_costs, "PnL with costs should be lower than without costs"
        # Difference should be the total costs
        cost_difference = pnl_no_costs - pnl_with_costs
        assert cost_difference > 0, "Cost difference should be positive"
    
    def test_unfilled_order_zero_pnl(self):
        """Test that unfilled order has zero PnL"""
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
        
        params = SupplyDemandParameters(stop_buffer_pct=0.0)
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        # Don't fill the order
        
        pnl = calculate_pnl_with_costs(trade_plan, 110.0, params)
        
        assert pnl == 0.0, "Unfilled order should have zero PnL"


class TestWickBasedFills:
    """Test that fills are based on OHLC wicks (high/low), not just close price"""
    
    def test_long_fills_on_wick_low_below_limit(self):
        """LONG limit at 100: candle low=99 (wick) → should fill"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Candle with wick down to 99 (below limit of 100), but closes at 105
        # This tests that we're using LOW (wick), not CLOSE
        candles = [
            {'open': 104, 'high': 106, 'low': 99, 'close': 105},  # Low=99 < limit=100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is True, "LONG order should fill when wick (low) touches limit, regardless of close"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == 0
        # Fill price should be limit (100.0), not the wick low (99)
        assert trade_plan.actual_entry_price is not None
    
    def test_short_fills_on_wick_high_above_limit(self):
        """SHORT limit at 100: candle high=101 (wick) → should fill"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 98.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Candle with wick up to 101 (above limit of 100), but closes at 95
        # This tests that we're using HIGH (wick), not CLOSE
        candles = [
            {'open': 96, 'high': 101, 'low': 94, 'close': 95},  # High=101 > limit=100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is True, "SHORT order should fill when wick (high) touches limit, regardless of close"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == 0
        assert trade_plan.actual_entry_price is not None
    
    def test_long_not_filled_when_wick_above_limit(self):
        """LONG limit at 100: candle low=101 (above limit) → should NOT fill"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Candle never touches limit (low=101 > limit=100)
        candles = [
            {'open': 105, 'high': 107, 'low': 101, 'close': 103},  # Low=101 > limit=100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is False, "LONG order should NOT fill when low never reaches limit"
        # Compare by value due to enum comparison issue
        assert trade_plan.order_state.value == 'pending'
    
    def test_short_not_filled_when_wick_below_limit(self):
        """SHORT limit at 100: candle high=99 (below limit) → should NOT fill"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 98.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        trade_plan.placed_at_idx = 0
        
        # Candle never touches limit (high=99 < limit=100)
        candles = [
            {'open': 95, 'high': 99, 'low': 93, 'close': 97},  # High=99 < limit=100
        ]
        
        filled = check_limit_order_fill(trade_plan, candles, 0, params)
        
        assert filled is False, "SHORT order should NOT fill when high never reaches limit"
        # Compare by value due to enum comparison issue
        assert trade_plan.order_state.value == 'pending'


class TestSameCandleFills:
    """Test that orders can fill on the same candle where they are placed"""
    
    def test_long_same_candle_fill(self):
        """Test LONG order fills on same candle if wick touches limit"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        
        # Simulate order placement at candle index 5
        placed_idx = 5
        trade_plan.placed_at_idx = placed_idx
        
        # Same candle where order is placed has wick touching limit
        candles = [
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},  # Dummy candles 0-4
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 104, 'high': 106, 'low': 99, 'close': 105},  # Index 5: low=99 touches limit=100
        ]
        
        # Check fill on the SAME candle where order was placed
        filled = check_limit_order_fill(trade_plan, candles, placed_idx, params)
        
        assert filled is True, "Order should fill on same candle if price touches limit"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == placed_idx
    
    def test_short_same_candle_fill(self):
        """Test SHORT order fills on same candle if wick touches limit"""
        zone = Zone(
            zone_type=ZoneType.SUPPLY,
            proximal=100.0,
            distal=105.0,
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 98.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        
        # Simulate order placement at candle index 3
        placed_idx = 3
        trade_plan.placed_at_idx = placed_idx
        
        # Same candle where order is placed has wick touching limit
        candles = [
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},  # Dummy candles 0-2
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 96, 'high': 101, 'low': 94, 'close': 95},  # Index 3: high=101 touches limit=100
        ]
        
        # Check fill on the SAME candle where order was placed
        filled = check_limit_order_fill(trade_plan, candles, placed_idx, params)
        
        assert filled is True, "Order should fill on same candle if price touches limit"
        assert trade_plan.order_state == OrderState.FILLED
        assert trade_plan.filled_at_idx == placed_idx
    
    def test_no_same_candle_fill_when_price_no_touch(self):
        """Test order does NOT fill on same candle if price doesn't touch limit"""
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
            ttl_bars=10
        )
        
        trade_plan = build_trade_plan(
            zone, 102.0, 10000.0, params, None
        )
        
        assert trade_plan is not None
        
        # Simulate order placement at candle index 2
        placed_idx = 2
        trade_plan.placed_at_idx = placed_idx
        
        # Same candle where order is placed does NOT touch limit (low=103 > limit=100)
        candles = [
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},  # Dummy candles
            {'open': 100, 'high': 100, 'low': 100, 'close': 100},
            {'open': 105, 'high': 107, 'low': 103, 'close': 106},  # Index 2: low=103 doesn't touch limit=100
        ]
        
        # Check fill on the SAME candle where order was placed
        filled = check_limit_order_fill(trade_plan, candles, placed_idx, params)
        
        assert filled is False, "Order should NOT fill if price doesn't touch limit"
        # Compare by value due to enum comparison issue
        assert trade_plan.order_state.value == 'pending'
