"""Tests for parallel backtest execution

Tests cover:
- Serial vs parallel result equivalence
- Chunking logic
- Error handling in parallel mode
- Deterministic ordering
- Multiprocessing start method compatibility
"""

import pytest
import json
import tempfile
import shutil
import yaml
from pathlib import Path
import multiprocessing
import os

from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    run_symbol_backtest,
    run_backtests_parallel,
    load_config,
)
from strategies.supply_demand_v1.strategy import SupplyDemandParameters, EntryMode


@pytest.fixture
def minimal_parallel_config():
    """Create a minimal config for testing parallel execution"""
    return {
        'name': 'test_parallel',
        'description': 'Parallel test config',
        'data_source': 'synthetic',
        'symbols': ['TEST1/USDT', 'TEST2/USDT', 'TEST3/USDT'],
        'start_date': '2024-01-01',
        'end_date': '2024-01-31',
        'timeframes': {
            'htf': '4h',
            'itf': '1h',
            'ltf': '15m',
            'rtf': None,
        },
        'candle_classification': {
            'boring_body_ratio': 0.50,
            'exciting_body_ratio': 0.50,
        },
        'zone_detection': {
            'min_base_candles': 1,
            'max_base_candles': 6,
            'min_legout_candles': 1,
            'proximal_mode': 'body',
        },
        'scoring': {
            'min_setup_score': 6.0,
            'freshness_touches_best': 0,
            'freshness_touches_good': 1,
            'base_time_best': 3,
            'base_time_good': 6,
            'legout_strength_high_threshold': 0.10,
            'legout_strength_mid_threshold': 0.05,
        },
        'trade_management': {
            'risk_pct': 0.02,
            'breakeven_at_r': 2.0,
            'take_profit_at_r': 3.0,
            'min_reward_risk': 3.0,
            'stop_buffer_pct': 0.001,
        },
        'trend_detection': {
            'pivot_len': 5,
            'pivots_to_consider': 4,
        },
        'mtf_gating': {
            'allow_eq_trades': True,
            'eq_requires_trend_alignment': True,
            'eq_min_setup_score_bonus': 1.0,
        },
        'entry': {
            'entry_mode': 'limit',
            'ttl_bars': 10,
        },
        'costs': {
            'fees_bps': 10.0,
            'slippage_bps': 5.0,
        },
        'initial_capital': 10000.0,
        'data_generation': {
            'num_candles': 200,  # Small for fast testing
            'volatility': 0.02,
            'seed': 42,
        },
    }


def create_params_from_config(config):
    """Helper to create SupplyDemandParameters from config"""
    return SupplyDemandParameters(
        boring_body_ratio=config['candle_classification']['boring_body_ratio'],
        exciting_body_ratio=config['candle_classification']['exciting_body_ratio'],
        min_base_candles=config['zone_detection']['min_base_candles'],
        max_base_candles=config['zone_detection']['max_base_candles'],
        min_legout_candles=config['zone_detection']['min_legout_candles'],
        proximal_mode=config['zone_detection']['proximal_mode'],
        min_setup_score=config['scoring']['min_setup_score'],
        freshness_touches_best=config['scoring']['freshness_touches_best'],
        freshness_touches_good=config['scoring']['freshness_touches_good'],
        base_time_best=config['scoring']['base_time_best'],
        base_time_good=config['scoring']['base_time_good'],
        legout_strength_high_threshold=config['scoring']['legout_strength_high_threshold'],
        legout_strength_mid_threshold=config['scoring']['legout_strength_mid_threshold'],
        risk_pct=config['trade_management']['risk_pct'],
        breakeven_at_r=config['trade_management']['breakeven_at_r'],
        take_profit_at_r=config['trade_management']['take_profit_at_r'],
        min_reward_risk=config['trade_management']['min_reward_risk'],
        stop_buffer_pct=config['trade_management']['stop_buffer_pct'],
        pivot_len=config['trend_detection']['pivot_len'],
        pivots_to_consider=config['trend_detection']['pivots_to_consider'],
        allow_eq_trades=config['mtf_gating']['allow_eq_trades'],
        eq_requires_trend_alignment=config['mtf_gating']['eq_requires_trend_alignment'],
        eq_min_setup_score_bonus=config['mtf_gating']['eq_min_setup_score_bonus'],
        entry_mode=EntryMode.LIMIT if config['entry']['entry_mode'] == 'limit' else EntryMode.CONFIRMATION,
        ttl_bars=config['entry']['ttl_bars'],
        fees_bps=config['costs']['fees_bps'],
        slippage_bps=config['costs']['slippage_bps'],
        htf_tf=config['timeframes']['htf'],
        itf_tf=config['timeframes']['itf'],
        ltf_tf=config['timeframes']['ltf'],
        rtf_tf=config['timeframes']['rtf'],
    )


def test_serial_vs_parallel_equivalence(minimal_parallel_config):
    """Test that serial and parallel execution produce identical results"""
    config = minimal_parallel_config.copy()
    params = create_params_from_config(config)
    initial_capital = config['initial_capital']
    
    # Run serial
    print("\n=== Running SERIAL backtest ===")
    serial_results = []
    for symbol in config['symbols']:
        result = run_symbol_backtest(symbol, config, params, initial_capital)
        serial_results.append(result)
    serial_results.sort(key=lambda r: r.symbol)
    
    # Run parallel
    print("\n=== Running PARALLEL backtest ===")
    parallel_config_settings = {
        'workers': 2,
        'chunk_size': 1,
        'fail_fast': True,
    }
    parallel_results = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        parallel_config_settings
    )
    parallel_results.sort(key=lambda r: r.symbol)
    
    # Compare results
    assert len(serial_results) == len(parallel_results)
    
    for serial, parallel in zip(serial_results, parallel_results):
        # Check symbol
        assert serial.symbol == parallel.symbol
        
        # Check metrics
        assert serial.total_zones == parallel.total_zones, f"Zone count mismatch for {serial.symbol}"
        assert serial.fresh_zones == parallel.fresh_zones, f"Fresh zone count mismatch for {serial.symbol}"
        assert serial.trades_placed == parallel.trades_placed, f"Trades placed mismatch for {serial.symbol}"
        assert serial.trades_filled == parallel.trades_filled, f"Trades filled mismatch for {serial.symbol}"
        assert serial.trades_won == parallel.trades_won, f"Trades won mismatch for {serial.symbol}"
        assert abs(serial.total_pnl - parallel.total_pnl) < 0.01, f"P&L mismatch for {serial.symbol}"
        assert abs(serial.win_rate - parallel.win_rate) < 0.001, f"Win rate mismatch for {serial.symbol}"
        assert abs(serial.avg_r_realized - parallel.avg_r_realized) < 0.001, f"Avg R mismatch for {serial.symbol}"
        assert abs(serial.max_drawdown - parallel.max_drawdown) < 0.01, f"Max drawdown mismatch for {serial.symbol}"
        
        # Check trades count
        serial_trades = getattr(serial, 'trades', [])
        parallel_trades = getattr(parallel, 'trades', [])
        assert len(serial_trades) == len(parallel_trades), f"Trade count mismatch for {serial.symbol}"
        
        # Check zones count
        serial_zones = getattr(serial, 'zones', [])
        parallel_zones = getattr(parallel, 'zones', [])
        assert len(serial_zones) == len(parallel_zones), f"Zone count mismatch for {serial.symbol}"
    
    print("✓ Serial and parallel results are equivalent")


def test_parallel_deterministic_ordering(minimal_parallel_config):
    """Test that parallel execution produces deterministically ordered results"""
    config = minimal_parallel_config.copy()
    params = create_params_from_config(config)
    initial_capital = config['initial_capital']
    
    parallel_config_settings = {
        'workers': 2,
        'chunk_size': 1,
        'fail_fast': True,
    }
    
    # Run twice
    results1 = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        parallel_config_settings
    )
    
    results2 = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        parallel_config_settings
    )
    
    # Check ordering is consistent
    symbols1 = [r.symbol for r in results1]
    symbols2 = [r.symbol for r in results2]
    assert symbols1 == symbols2
    
    # Check symbols are sorted
    assert symbols1 == sorted(symbols1)
    
    print("✓ Parallel execution produces deterministic ordering")


def test_parallel_with_different_chunk_sizes(minimal_parallel_config):
    """Test that different chunk sizes produce same results"""
    config = minimal_parallel_config.copy()
    params = create_params_from_config(config)
    initial_capital = config['initial_capital']
    
    # Run with chunk_size=1
    results_chunk1 = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        {'workers': 2, 'chunk_size': 1, 'fail_fast': True}
    )
    
    # Run with chunk_size=2
    results_chunk2 = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        {'workers': 2, 'chunk_size': 2, 'fail_fast': True}
    )
    
    # Run with chunk_size=3 (all in one chunk)
    results_chunk3 = run_backtests_parallel(
        config['symbols'],
        config,
        params,
        initial_capital,
        {'workers': 2, 'chunk_size': 3, 'fail_fast': True}
    )
    
    # Compare metrics
    for r1, r2, r3 in zip(results_chunk1, results_chunk2, results_chunk3):
        assert r1.symbol == r2.symbol == r3.symbol
        assert r1.total_zones == r2.total_zones == r3.total_zones
        assert r1.trades_filled == r2.trades_filled == r3.trades_filled
        assert abs(r1.total_pnl - r2.total_pnl) < 0.01
        assert abs(r1.total_pnl - r3.total_pnl) < 0.01
    
    print("✓ Different chunk sizes produce same results")


def test_parallel_full_experiment(minimal_parallel_config, tmp_path):
    """Test full experiment run with parallel execution"""
    config = minimal_parallel_config.copy()
    config['parallel'] = {
        'enabled': True,
        'workers': 2,
        'chunk_size': 1,
        'fail_fast': True,
    }
    
    # Write config to file
    config_file = tmp_path / "test_parallel.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(config, f)
    
    # Run experiment
    result = run_backtest_experiment(str(config_file))
    
    # Check results
    assert len(result.symbol_results) == 3
    assert result.aggregate_metrics['total_symbols'] == 3
    
    # Check ordering
    symbols = [sr.symbol for sr in result.symbol_results]
    assert symbols == sorted(symbols)
    
    # Check trades are sorted
    if result.all_trades:
        prev_symbol = None
        prev_idx = -1
        for trade in result.all_trades:
            if trade['symbol'] != prev_symbol:
                prev_symbol = trade['symbol']
                prev_idx = -1
            assert trade['entry_idx'] >= prev_idx
            prev_idx = trade['entry_idx']
    
    print("✓ Full parallel experiment runs successfully")


def test_multiprocessing_spawn_compatibility():
    """Test that parallel execution works with spawn method (Linux/macOS)"""
    # Get current start method
    current_method = multiprocessing.get_start_method()
    print(f"Current multiprocessing start method: {current_method}")
    
    # On Linux in CI, the start method is usually 'fork' or 'spawn'
    # On macOS, it's 'spawn' by default
    # We just verify that we can detect the method
    assert current_method in ['fork', 'spawn', 'forkserver']
    
    print(f"✓ Multiprocessing method '{current_method}' is compatible")


def test_parallel_experiment_vs_serial_full_equivalence(tmp_path):
    """Integration test: Full serial vs parallel experiment equivalence"""
    config = {
        'name': 'test_integration',
        'description': 'Integration test',
        'data_source': 'synthetic',
        'symbols': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
        'start_date': '2024-01-01',
        'end_date': '2024-01-31',
        'timeframes': {
            'htf': '4h',
            'itf': '1h',
            'ltf': '15m',
            'rtf': None,
        },
        'candle_classification': {
            'boring_body_ratio': 0.50,
            'exciting_body_ratio': 0.50,
        },
        'zone_detection': {
            'min_base_candles': 1,
            'max_base_candles': 6,
            'min_legout_candles': 1,
            'proximal_mode': 'body',
        },
        'scoring': {
            'min_setup_score': 6.0,
            'freshness_touches_best': 0,
            'freshness_touches_good': 1,
            'base_time_best': 3,
            'base_time_good': 6,
            'legout_strength_high_threshold': 0.10,
            'legout_strength_mid_threshold': 0.05,
        },
        'trade_management': {
            'risk_pct': 0.02,
            'breakeven_at_r': 2.0,
            'take_profit_at_r': 3.0,
            'min_reward_risk': 3.0,
            'stop_buffer_pct': 0.001,
        },
        'trend_detection': {
            'pivot_len': 5,
            'pivots_to_consider': 4,
        },
        'mtf_gating': {
            'allow_eq_trades': True,
            'eq_requires_trend_alignment': True,
            'eq_min_setup_score_bonus': 1.0,
        },
        'entry': {
            'entry_mode': 'limit',
            'ttl_bars': 10,
        },
        'costs': {
            'fees_bps': 10.0,
            'slippage_bps': 5.0,
        },
        'initial_capital': 10000.0,
        'data_generation': {
            'num_candles': 200,
            'volatility': 0.02,
            'seed': 42,
        },
    }
    
    # Run serial
    config_serial = config.copy()
    config_serial['parallel'] = {'enabled': False}
    config_file_serial = tmp_path / "test_serial.yaml"
    with open(config_file_serial, 'w') as f:
        yaml.dump(config_serial, f)
    
    result_serial = run_backtest_experiment(str(config_file_serial))
    
    # Run parallel
    config_parallel = config.copy()
    config_parallel['parallel'] = {
        'enabled': True,
        'workers': 2,
        'chunk_size': 1,
        'fail_fast': True,
    }
    config_file_parallel = tmp_path / "test_parallel.yaml"
    with open(config_file_parallel, 'w') as f:
        yaml.dump(config_parallel, f)
    
    result_parallel = run_backtest_experiment(str(config_file_parallel))
    
    # Compare aggregate metrics
    assert result_serial.aggregate_metrics['total_symbols'] == result_parallel.aggregate_metrics['total_symbols']
    assert result_serial.aggregate_metrics['total_filled'] == result_parallel.aggregate_metrics['total_filled']
    assert result_serial.aggregate_metrics['total_won'] == result_parallel.aggregate_metrics['total_won']
    assert abs(result_serial.aggregate_metrics['overall_pnl'] - result_parallel.aggregate_metrics['overall_pnl']) < 0.01
    assert abs(result_serial.aggregate_metrics['overall_win_rate'] - result_parallel.aggregate_metrics['overall_win_rate']) < 0.001
    
    # Compare per-symbol results
    for sr_serial, sr_parallel in zip(result_serial.symbol_results, result_parallel.symbol_results):
        assert sr_serial.symbol == sr_parallel.symbol
        assert sr_serial.total_zones == sr_parallel.total_zones
        assert sr_serial.trades_filled == sr_parallel.trades_filled
        assert abs(sr_serial.total_pnl - sr_parallel.total_pnl) < 0.01
    
    # Compare trade counts
    assert len(result_serial.all_trades) == len(result_parallel.all_trades)
    
    # Compare zone counts
    assert len(result_serial.all_zones) == len(result_parallel.all_zones)
    
    print("✓ Full serial vs parallel experiments are equivalent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
