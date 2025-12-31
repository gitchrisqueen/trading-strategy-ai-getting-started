"""Tests for Supply & Demand V1 experiment runner

Tests cover:
- Runner can execute with minimal config
- Artifacts are generated with expected structure
- Required CSV columns are present
- Integrity checks are performed
"""

import pytest
import json
import csv
from pathlib import Path
import tempfile
import shutil
import yaml

from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    write_artifacts,
    generate_synthetic_candles,
    execute_backtest_for_symbol,
    ExperimentResult,
)
from strategies.supply_demand_v1.strategy import SupplyDemandParameters


@pytest.fixture
def minimal_config():
    """Create a minimal config for testing"""
    return {
        'name': 'test_experiment',
        'description': 'Minimal test config',
        'symbols': ['TEST/USDT'],
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


@pytest.fixture
def temp_config_file(minimal_config):
    """Create a temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(minimal_config, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    Path(config_path).unlink(missing_ok=True)


@pytest.fixture
def temp_artifacts_dir():
    """Create a temporary artifacts directory"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestSyntheticDataGeneration:
    """Test synthetic candle generation"""
    
    def test_generate_candles_deterministic(self):
        """Test that candle generation is deterministic with same seed"""
        candles1 = generate_synthetic_candles('BTC/USDT', 100, seed=42)
        candles2 = generate_synthetic_candles('BTC/USDT', 100, seed=42)
        
        assert len(candles1) == len(candles2) == 100
        
        # Check same prices
        for c1, c2 in zip(candles1, candles2):
            assert c1['open'] == c2['open']
            assert c1['high'] == c2['high']
            assert c1['low'] == c2['low']
            assert c1['close'] == c2['close']
    
    def test_generate_candles_structure(self):
        """Test that generated candles have correct structure"""
        candles = generate_synthetic_candles('ETH/USDT', 50, seed=123)
        
        assert len(candles) == 50
        
        for candle in candles:
            # Check all required fields present
            assert 'open' in candle
            assert 'high' in candle
            assert 'low' in candle
            assert 'close' in candle
            assert 'volume' in candle
            assert 'timestamp' in candle
            assert 'symbol' in candle
            
            # Check OHLC relationships
            assert candle['high'] >= candle['open']
            assert candle['high'] >= candle['close']
            assert candle['low'] <= candle['open']
            assert candle['low'] <= candle['close']
            assert candle['high'] >= candle['low']


class TestRunnerExecution:
    """Test runner execution and artifact generation"""
    
    def test_runner_executes_successfully(self, temp_config_file):
        """Test that runner executes without errors"""
        result = run_backtest_experiment(temp_config_file)
        
        assert result is not None
        assert isinstance(result, ExperimentResult)
        assert len(result.symbol_results) > 0
        assert result.aggregate_metrics is not None
        assert result.integrity_report is not None
    
    def test_artifacts_created(self, temp_config_file, temp_artifacts_dir):
        """Test that all required artifact files are created"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        # Check all required files exist
        assert (temp_artifacts_dir / 'summary.json').exists()
        assert (temp_artifacts_dir / 'trades.csv').exists()
        assert (temp_artifacts_dir / 'zones.csv').exists()
        assert (temp_artifacts_dir / 'run_manifest.json').exists()
        assert (temp_artifacts_dir / 'violations.json').exists()
    
    def test_summary_json_structure(self, temp_config_file, temp_artifacts_dir):
        """Test that summary.json has expected structure"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'summary.json', 'r') as f:
            summary = json.load(f)
        
        # Check aggregate metrics
        assert 'aggregate_metrics' in summary
        assert 'total_symbols' in summary['aggregate_metrics']
        assert 'total_trades' in summary['aggregate_metrics']
        assert 'overall_win_rate' in summary['aggregate_metrics']
        
        # Check symbol results
        assert 'symbol_results' in summary
        assert len(summary['symbol_results']) > 0
        
        for symbol_result in summary['symbol_results']:
            assert 'symbol' in symbol_result
            assert 'total_zones' in symbol_result
            assert 'trades_filled' in symbol_result
            assert 'win_rate' in symbol_result
    
    def test_trades_csv_columns(self, temp_config_file, temp_artifacts_dir):
        """Test that trades.csv has all required columns"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'trades.csv', 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Check required columns
            required_columns = [
                'symbol', 'side', 'entry', 'stop', 'target',
                'planned_R', 'realized_R', 'entry_time', 'exit_time',
                'exit_reason', 'score', 'pnl'
            ]
            
            for col in required_columns:
                assert col in fieldnames, f"Missing required column: {col}"
    
    def test_zones_csv_columns(self, temp_config_file, temp_artifacts_dir):
        """Test that zones.csv has expected columns"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'zones.csv', 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Check expected columns
            expected_columns = [
                'symbol', 'zone_type', 'proximal', 'distal',
                'created_at', 'base_len', 'legout_return',
                'freshness_touches', 'is_fresh'
            ]
            
            for col in expected_columns:
                assert col in fieldnames, f"Missing expected column: {col}"
    
    def test_run_manifest_content(self, temp_config_file, temp_artifacts_dir):
        """Test that run_manifest.json has required metadata"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'run_manifest.json', 'r') as f:
            manifest = json.load(f)
        
        # Check required fields
        assert 'timestamp' in manifest
        assert 'git_commit' in manifest
        assert 'python_version' in manifest
        assert 'config_file' in manifest
        assert 'config_hash' in manifest
    
    def test_violations_json_structure(self, temp_config_file, temp_artifacts_dir):
        """Test that violations.json has expected structure"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'violations.json', 'r') as f:
            violations = json.load(f)
        
        # Check required fields
        assert 'total_trades' in violations
        assert 'clean' in violations
        assert 'violation_counts' in violations
        assert 'violations' in violations
        assert isinstance(violations['violations'], list)


class TestIntegrityChecks:
    """Test integrity validation"""
    
    def test_integrity_report_created(self, temp_config_file):
        """Test that integrity report is created"""
        result = run_backtest_experiment(temp_config_file)
        
        assert result.integrity_report is not None
        assert hasattr(result.integrity_report, 'total_trades')
        assert hasattr(result.integrity_report, 'violations')
        assert hasattr(result.integrity_report, 'clean')
    
    def test_minimum_r_validation(self, temp_config_file):
        """Test that minimum R validation is performed"""
        result = run_backtest_experiment(temp_config_file)
        
        # Integrity report should exist
        assert result.integrity_report is not None
        
        # If there are trades, check for R violations
        if result.all_trades:
            # Check that validation was performed
            # (violations may or may not exist depending on the data)
            assert isinstance(result.integrity_report.violations, list)


class TestSymbolBacktest:
    """Test single symbol backtest execution"""
    
    def test_execute_backtest_for_symbol(self):
        """Test executing backtest for a single symbol"""
        params = SupplyDemandParameters()
        candles = generate_synthetic_candles('BTC/USDT', 200, seed=42)
        
        trades, zones, final_capital = execute_backtest_for_symbol(
            'BTC/USDT',
            candles,
            params,
            10000.0
        )
        
        # Check outputs exist
        assert isinstance(trades, list)
        assert isinstance(zones, list)
        assert isinstance(final_capital, float)
        
        # Check zones were detected
        assert len(zones) > 0
        
        # Check zone structure
        for zone in zones:
            assert 'symbol' in zone
            assert 'zone_type' in zone
            assert 'proximal' in zone
            assert 'distal' in zone
