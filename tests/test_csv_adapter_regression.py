"""Regression tests for CSV backtest adapter

These tests ensure that the CSV backtest adapter maintains backward compatibility
and produces stable, deterministic results after the compatibility layer refactoring.

Key validations:
1. Experiment runs without errors
2. Artifact schema remains stable (no field removals)
3. Results are deterministic (same config → same metrics)
"""

import pytest
import json
import csv
from pathlib import Path
import tempfile
import shutil

# Import from runner (which re-exports from csv_backtest_adapter)
from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    write_artifacts,
    create_artifacts_folder,
)


@pytest.fixture
def test_config_path(tmp_path):
    """Create a minimal test config for fast execution"""
    config = {
        'name': 'test_regression',
        'description': 'Regression test config',
        'data_source': 'synthetic',
        'symbols': ['BTC/USDT'],  # Single symbol for speed
        'start_date': '2024-01-01',
        'end_date': '2024-01-31',  # Short window
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
            'num_candles': 500,  # Small for speed
            'volatility': 0.02,
            'seed': 42,  # Fixed seed for determinism
        },
    }
    
    config_path = tmp_path / "test_config.yaml"
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    
    return str(config_path)


def test_csv_adapter_runs_without_error(test_config_path):
    """Test that CSV adapter can run an experiment without raising exceptions"""
    result = run_backtest_experiment(test_config_path)
    
    # Basic sanity checks
    assert result is not None
    assert hasattr(result, 'aggregate_metrics')
    assert hasattr(result, 'symbol_results')
    assert hasattr(result, 'all_trades')
    assert hasattr(result, 'all_zones')
    assert hasattr(result, 'integrity_report')


def test_artifact_schema_stable(test_config_path, tmp_path):
    """Test that artifact files are generated with expected schemas"""
    # Run experiment
    result = run_backtest_experiment(test_config_path)
    
    # Write artifacts to temp directory
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    write_artifacts(result, artifacts_dir)
    
    # Check that all expected files exist
    expected_files = [
        'summary.json',
        'trades.csv',
        'zones.csv',
        'orders.csv',
        'run_manifest.json',
        'violations.json',
        'metrics_warnings.json',
        'decision_funnel.json',
    ]
    
    for filename in expected_files:
        filepath = artifacts_dir / filename
        assert filepath.exists(), f"Missing artifact file: {filename}"
    
    # Validate summary.json schema
    with open(artifacts_dir / 'summary.json') as f:
        summary = json.load(f)
    
    assert 'aggregate_metrics' in summary
    assert 'symbol_results' in summary
    
    # Check key aggregate_metrics fields
    agg = summary['aggregate_metrics']
    required_agg_fields = [
        'total_symbols',
        'total_trades',
        'total_filled',
        'total_won',
        'total_lost',
        'overall_win_rate',
        'overall_pnl',
        'avg_r_realized',
    ]
    for field in required_agg_fields:
        assert field in agg, f"Missing aggregate_metrics field: {field}"
    
    # Validate trades.csv schema
    with open(artifacts_dir / 'trades.csv') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        
        # These fields must exist (even if file is empty)
        expected_trade_fields = ['symbol', 'side', 'entry', 'stop', 'target', 'planned_R']
        for field in expected_trade_fields:
            assert field in headers, f"Missing trades.csv field: {field}"
    
    # Validate zones.csv schema
    with open(artifacts_dir / 'zones.csv') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        
        expected_zone_fields = ['symbol', 'zone_type', 'proximal', 'distal']
        for field in expected_zone_fields:
            assert field in headers, f"Missing zones.csv field: {field}"
    
    # Validate run_manifest.json schema
    with open(artifacts_dir / 'run_manifest.json') as f:
        manifest = json.load(f)
    
    required_manifest_fields = [
        'timestamp',
        'git_commit',
        'python_version',
        'config_file',
        'data_source',
    ]
    for field in required_manifest_fields:
        assert field in manifest, f"Missing run_manifest.json field: {field}"


def test_deterministic_results(test_config_path):
    """Test that running the same config twice produces identical metrics"""
    # Run experiment twice
    result1 = run_backtest_experiment(test_config_path)
    result2 = run_backtest_experiment(test_config_path)
    
    # Compare aggregate metrics
    agg1 = result1.aggregate_metrics
    agg2 = result2.aggregate_metrics
    
    # These metrics should be exactly identical
    assert agg1['total_symbols'] == agg2['total_symbols']
    assert agg1['total_trades'] == agg2['total_trades']
    assert agg1['total_filled'] == agg2['total_filled']
    assert agg1['total_won'] == agg2['total_won']
    assert agg1['total_lost'] == agg2['total_lost']
    
    # Floating point metrics should be very close (within 1e-6)
    assert abs(agg1['overall_win_rate'] - agg2['overall_win_rate']) < 1e-6
    assert abs(agg1['overall_pnl'] - agg2['overall_pnl']) < 1e-6
    assert abs(agg1['avg_r_realized'] - agg2['avg_r_realized']) < 1e-6
    
    # Compare number of zones and trades
    assert len(result1.all_zones) == len(result2.all_zones)
    assert len(result1.all_trades) == len(result2.all_trades)


def test_csv_adapter_imports_from_strategy_core():
    """Test that csv_backtest_adapter properly imports from strategy_core"""
    # Import csv_backtest_adapter
    import strategies.supply_demand_v1.csv_backtest_adapter as adapter
    
    # Check that it imports from strategy module (which re-exports from strategy_core)
    # This validates the import chain works correctly
    assert hasattr(adapter, 'detect_zones_dbr_rbd')
    assert hasattr(adapter, 'odds_enhancer_score')
    assert hasattr(adapter, 'should_allow_trade')
    assert hasattr(adapter, 'build_trade_plan')


def test_runner_backward_compatibility():
    """Test that runner.py re-exports functions from csv_backtest_adapter"""
    from strategies.supply_demand_v1 import runner
    
    # Check that key functions are available from runner
    assert hasattr(runner, 'run_backtest_experiment')
    assert hasattr(runner, 'execute_backtest_for_symbol')
    assert hasattr(runner, 'write_artifacts')
    assert hasattr(runner, 'create_artifacts_folder')
    assert hasattr(runner, 'generate_synthetic_candles_mtf')
    
    # Verify they're the same functions (not copies)
    from strategies.supply_demand_v1.csv_backtest_adapter import (
        run_backtest_experiment as csv_run_backtest,
        write_artifacts as csv_write_artifacts,
    )
    
    assert runner.run_backtest_experiment is csv_run_backtest
    assert runner.write_artifacts is csv_write_artifacts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
