"""Unit tests for trade lifecycle simulation

Tests cover:
- Positions held across multiple bars (exit_idx > entry_idx)
- Stop loss hits on later bars
- Take profit hits on later bars
- Both stop and target hit on same bar (stop wins by default)
- EOD close for open positions
- Exit reason normalization (strings not dicts)
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
    check_intrabar_exit,
)


class TestIntrabarExitDetection:
    """Test intrabar exit detection logic"""
    
    def test_long_stop_hit(self):
        """Test that long position exits when stop is hit"""
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
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Candle where low hits stop (95.0)
        candle = {'open': 98, 'high': 99, 'low': 94, 'close': 95}
        
        exit_reason = check_intrabar_exit(trade_plan, candle, params)
        
        assert exit_reason == "STOP", "Long position should exit when stop is hit"
    
    def test_long_target_hit(self):
        """Test that long position exits when target is hit"""
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
            min_reward_risk=3.0,
        )
        
        trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Expected target: 100 + 3 * (100 - 95) = 115
        # Candle where high hits target
        candle = {'open': 110, 'high': 116, 'low': 109, 'close': 115}
        
        exit_reason = check_intrabar_exit(trade_plan, candle, params)
        
        assert exit_reason == "TARGET", "Long position should exit when target is hit"
    
    def test_long_no_exit(self):
        """Test that long position stays open when neither stop nor target hit"""
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
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Candle that doesn't hit stop or target
        candle = {'open': 102, 'high': 105, 'low': 99, 'close': 103}
        
        exit_reason = check_intrabar_exit(trade_plan, candle, params)
        
        assert exit_reason is None, "Position should stay open"
    
    def test_short_stop_hit(self):
        """Test that short position exits when stop is hit"""
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
        )
        
        trade_plan = build_trade_plan(zone, 98.0, 10000.0, params, None)
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Candle where high hits stop (105.0)
        candle = {'open': 102, 'high': 106, 'low': 101, 'close': 103}
        
        exit_reason = check_intrabar_exit(trade_plan, candle, params)
        
        assert exit_reason == "STOP", "Short position should exit when stop is hit"
    
    def test_short_target_hit(self):
        """Test that short position exits when target is hit"""
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
            min_reward_risk=3.0,
        )
        
        trade_plan = build_trade_plan(zone, 98.0, 10000.0, params, None)
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Expected target: 100 - 3 * (105 - 100) = 85
        # Candle where low hits target
        candle = {'open': 88, 'high': 90, 'low': 84, 'close': 86}
        
        exit_reason = check_intrabar_exit(trade_plan, candle, params)
        
        assert exit_reason == "TARGET", "Short position should exit when target is hit"
    
    def test_both_hit_stop_wins(self):
        """Test that when both stop and target hit on same bar, stop wins"""
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
            min_reward_risk=3.0,
        )
        
        trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Wide-ranging candle that hits both stop (95) and target (115)
        candle = {'open': 100, 'high': 120, 'low': 90, 'close': 105}
        
        exit_reason = check_intrabar_exit(
            trade_plan, candle, params, stop_wins_on_same_bar=True
        )
        
        assert exit_reason == "STOP", "Stop should win when both hit on same bar (conservative)"
    
    def test_both_hit_target_wins_when_configured(self):
        """Test that target can win if configured"""
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
            min_reward_risk=3.0,
        )
        
        trade_plan = build_trade_plan(zone, 102.0, 10000.0, params, None)
        assert trade_plan is not None
        
        # Simulate fill
        trade_plan.order_state = OrderState.FILLED
        trade_plan.filled_at_idx = 5
        trade_plan.actual_entry_price = 100.0
        
        # Wide-ranging candle that hits both stop (95) and target (115)
        candle = {'open': 100, 'high': 120, 'low': 90, 'close': 105}
        
        exit_reason = check_intrabar_exit(
            trade_plan, candle, params, stop_wins_on_same_bar=False
        )
        
        assert exit_reason == "TARGET", "Target should win when configured"


class TestLifecycleSimulation:
    """Test complete lifecycle: fill on bar N, exit on bar N+K"""
    
    def test_position_held_multiple_bars_before_target(self):
        """Test that position is held across multiple bars until target hit"""
        from strategies.supply_demand_v1.runner import execute_backtest_for_symbol
        
        params = SupplyDemandParameters(
            min_base_candles=1,
            max_base_candles=6,
            min_setup_score=0.0,  # Accept all setups for test
            min_reward_risk=2.0,
            stop_buffer_pct=0.01,
            fees_bps=10.0,
            slippage_bps=5.0,
            ttl_bars=50,
        )
        
        # Create synthetic candles with:
        # - DBR zone early on
        # - Price returns to zone and fills
        # - Price then moves up to hit target several bars later
        candles = []
        
        # Candles 0-3: Create DBR zone
        candles.append({'open': 110, 'high': 110, 'low': 100, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})  # Drop
        candles.append({'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})  # Base
        candles.append({'open': 100, 'high': 110, 'low': 100, 'close': 110, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})  # Rally
        
        # Candles 3-120: Move away, then return
        for i in range(120):
            candles.append({'open': 110, 'high': 115, 'low': 109, 'close': 112, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Candles 121-125: Return to zone and fill
        candles.append({'open': 112, 'high': 112, 'low': 100, 'close': 101, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})  # Fill at 101
        
        # Candles 126-130: Hold position (no exit yet)
        for i in range(5):
            candles.append({'open': 101, 'high': 105, 'low': 100, 'close': 103, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Candle 131: Hit target
        # Entry ~101, Stop ~99, Risk ~2, Target ~107 (2R minimum)
        candles.append({'open': 103, 'high': 110, 'low': 103, 'close': 108, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})  # Target hit
        
        trades, zones, final_capital = execute_backtest_for_symbol(
            'TEST/USDT',
            candles,
            params,
            10000.0
        )
        
        # Should have at least one filled trade
        filled_trades = [t for t in trades if t['exit_idx'] is not None]
        assert len(filled_trades) > 0, "Should have at least one filled trade"
        
        # Check that exit_idx > entry_idx (position held across bars)
        for trade in filled_trades:
            assert trade['exit_idx'] > trade['entry_idx'], \
                f"exit_idx ({trade['exit_idx']}) should be > entry_idx ({trade['entry_idx']})"
        
        # Check exit reason is a string
        for trade in filled_trades:
            assert isinstance(trade['exit_reason'], str), \
                f"exit_reason should be string, got {type(trade['exit_reason'])}"
            assert trade['exit_reason'] in ['STOP', 'TARGET', 'EOD_CLOSE'], \
                f"exit_reason should be STOP, TARGET, or EOD_CLOSE, got {trade['exit_reason']}"
    
    def test_stop_hit_on_later_bar(self):
        """Test that position exits with STOP when stop is hit later"""
        from strategies.supply_demand_v1.runner import execute_backtest_for_symbol
        
        params = SupplyDemandParameters(
            min_base_candles=1,
            max_base_candles=6,
            min_setup_score=0.0,
            min_reward_risk=2.0,
            stop_buffer_pct=0.01,
            fees_bps=10.0,
            slippage_bps=5.0,
            ttl_bars=50,
        )
        
        candles = []
        
        # Create DBR zone
        candles.append({'open': 110, 'high': 110, 'low': 100, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        candles.append({'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        candles.append({'open': 100, 'high': 110, 'low': 100, 'close': 110, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Move away
        for i in range(100):
            candles.append({'open': 110, 'high': 115, 'low': 109, 'close': 112, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Return and fill
        candles.append({'open': 112, 'high': 112, 'low': 100, 'close': 101, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Hold for a few bars
        for i in range(3):
            candles.append({'open': 101, 'high': 102, 'low': 100, 'close': 101, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Hit stop (should be around 99 with buffer)
        candles.append({'open': 100, 'high': 100, 'low': 95, 'close': 96, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        trades, zones, final_capital = execute_backtest_for_symbol(
            'TEST/USDT',
            candles,
            params,
            10000.0
        )
        
        filled_trades = [t for t in trades if t['exit_idx'] is not None]
        assert len(filled_trades) > 0, "Should have filled trades"
        
        # At least one should have STOP exit
        stop_exits = [t for t in filled_trades if t['exit_reason'] == 'STOP']
        assert len(stop_exits) > 0, "Should have at least one STOP exit"
        
        # Verify holding period
        for trade in stop_exits:
            assert trade['exit_idx'] > trade['entry_idx'], "Should hold position across bars"
    
    def test_eod_close_for_open_positions(self):
        """Test that open positions are closed at end of data with EOD_CLOSE"""
        from strategies.supply_demand_v1.runner import execute_backtest_for_symbol
        
        params = SupplyDemandParameters(
            min_base_candles=1,
            max_base_candles=6,
            min_setup_score=0.0,
            min_reward_risk=2.0,
            stop_buffer_pct=0.01,
            fees_bps=10.0,
            slippage_bps=5.0,
            ttl_bars=50,
        )
        
        candles = []
        
        # Create DBR zone
        candles.append({'open': 110, 'high': 110, 'low': 100, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        candles.append({'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        candles.append({'open': 100, 'high': 110, 'low': 100, 'close': 110, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Move away
        for i in range(100):
            candles.append({'open': 110, 'high': 115, 'low': 109, 'close': 112, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Return and fill
        candles.append({'open': 112, 'high': 112, 'low': 100, 'close': 101, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        # Hold position to end (neither stop nor target hit)
        for i in range(10):
            candles.append({'open': 101, 'high': 104, 'low': 100, 'close': 102, 'volume': 1000, 'timestamp': None, 'symbol': 'TEST/USDT'})
        
        trades, zones, final_capital = execute_backtest_for_symbol(
            'TEST/USDT',
            candles,
            params,
            10000.0
        )
        
        filled_trades = [t for t in trades if t['exit_idx'] is not None]
        assert len(filled_trades) > 0, "Should have filled trades"
        
        # Check for EOD_CLOSE
        eod_exits = [t for t in filled_trades if t['exit_reason'] == 'EOD_CLOSE']
        assert len(eod_exits) > 0, "Should have at least one EOD_CLOSE"
        
        # Verify exit is at last candle
        for trade in eod_exits:
            assert trade['exit_idx'] == len(candles) - 1, "EOD_CLOSE should exit at last candle"
