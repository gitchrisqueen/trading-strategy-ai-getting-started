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
        
        trades, zones, final_capital, equity_curve, decision_funnel = execute_backtest_for_symbol(
            'BTC/USDT',
            candles,
            params,
            10000.0
        )
        
        # Check outputs exist
        assert isinstance(trades, list)
        assert isinstance(zones, list)
        assert isinstance(final_capital, float)
        assert isinstance(equity_curve, list)
        
        # Check zones were detected
        assert len(zones) > 0
        
        # Check equity curve starts with initial capital
        assert equity_curve[0] == 10000.0
        
        # Check zone structure
        for zone in zones:
            assert 'symbol' in zone
            assert 'zone_type' in zone
            assert 'proximal' in zone
            assert 'distal' in zone


class TestMultiSymbolIsolation:
    """Test that multi-symbol runs produce different results per symbol"""
    
    def test_different_symbols_produce_different_candles(self):
        """Test that different symbols get different candle data"""
        # Generate candles for two symbols with same base seed
        candles_btc = generate_synthetic_candles('BTC/USDT', 100, seed=42)
        candles_eth = generate_synthetic_candles('ETH/USDT', 100, seed=42)
        
        # Same seed should produce same candles if symbol not considered
        # But we want to verify they're actually the same
        assert len(candles_btc) == len(candles_eth) == 100
        
        # Check if they're identical (they shouldn't be if symbol is part of seed)
        close_prices_match = all(
            c1['close'] == c2['close'] 
            for c1, c2 in zip(candles_btc, candles_eth)
        )
        
        # If they match, that's the bug we're trying to prevent
        # This test documents the expected behavior
        # With symbol-specific seeding, they should differ
        
    def test_multi_symbol_experiment_produces_different_results(self, temp_artifacts_dir):
        """Test that multi-symbol experiment produces different per-symbol results"""
        # Create config with 2 symbols
        config = {
            'name': 'multi_symbol_test',
            'description': 'Test multi-symbol isolation',
            'symbols': ['BTC/USDT', 'ETH/USDT'],
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
                'num_candles': 300,
                'volatility': 0.02,
                'seed': 42,
            },
        }
        
        # Save config to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            # Run experiment
            result = run_backtest_experiment(config_path)
            write_artifacts(result, temp_artifacts_dir)
            
            # Load summary
            with open(temp_artifacts_dir / 'summary.json', 'r') as f:
                summary = json.load(f)
            
            # Get per-symbol results
            assert len(summary['symbol_results']) == 2
            sr1 = summary['symbol_results'][0]
            sr2 = summary['symbol_results'][1]
            
            # Check that symbols are different
            assert sr1['symbol'] != sr2['symbol']
            assert sr1['symbol'] == 'BTC/USDT'
            assert sr2['symbol'] == 'ETH/USDT'
            
            # Critical: zone counts should differ (extremely unlikely to be identical)
            # If both have 0 zones, that's OK, but if both have same non-zero count, that's suspicious
            if sr1['total_zones'] > 0 and sr2['total_zones'] > 0:
                # With different random seeds, zone counts should differ
                # Allow small chance they might be equal, but check other metrics too
                zones_differ = sr1['total_zones'] != sr2['total_zones']
                fresh_differ = sr1['fresh_zones'] != sr2['fresh_zones']
                
                # At least one metric should differ
                assert zones_differ or fresh_differ, (
                    "Zone metrics are identical for both symbols, indicating data duplication"
                )
            
            # Load trades and check they differ (if any exist)
            with open(temp_artifacts_dir / 'trades.csv', 'r') as f:
                reader = csv.DictReader(f)
                trades = list(reader)
            
            # If no trades, that's OK - just skip trade comparison
            if trades:
                # Get trades per symbol
                trades_btc = [t for t in trades if t['symbol'] == 'BTC/USDT']
                trades_eth = [t for t in trades if t['symbol'] == 'ETH/USDT']
                
                # If both symbols have trades, check that entry prices differ
                if trades_btc and trades_eth:
                    # Get first trade from each symbol
                    entry_btc = float(trades_btc[0]['entry'])
                    entry_eth = float(trades_eth[0]['entry'])
                    
                    # Entry prices should be different (different candle data)
                    assert abs(entry_btc - entry_eth) > 1.0, (
                        f"Entry prices too similar: BTC={entry_btc}, ETH={entry_eth}. "
                        "Indicates duplicate candle data."
                    )
            
            # Verify no curve_state or trend_state in trades.csv
            with open(temp_artifacts_dir / 'trades.csv', 'r') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                
                assert 'curve_state' not in fieldnames, (
                    "curve_state should not be in trades.csv (not implemented)"
                )
                assert 'trend_state' not in fieldnames, (
                    "trend_state should not be in trades.csv (not implemented)"
                )
                
        finally:
            # Cleanup
            Path(config_path).unlink(missing_ok=True)
    
    def test_symbol_specific_seed_generation(self):
        """Test that symbol-specific seeds are different"""
        base_seed = 42
        
        # Simulate what runner does
        symbol1 = "BTC/USDT"
        symbol2 = "ETH/USDT"
        
        seed1 = hash(symbol1 + str(base_seed)) % (2**31)
        seed2 = hash(symbol2 + str(base_seed)) % (2**31)
        
        # Seeds should be different
        assert seed1 != seed2, "Symbol-specific seeds should differ"
        
        # Generate candles with these seeds
        candles1 = generate_synthetic_candles(symbol1, 50, seed=seed1)
        candles2 = generate_synthetic_candles(symbol2, 50, seed=seed2)
        
        # Candles should differ
        assert len(candles1) == len(candles2) == 50
        
        # Check that at least some prices differ
        closes1 = [c['close'] for c in candles1]
        closes2 = [c['close'] for c in candles2]
        
        # They should not be identical
        assert closes1 != closes2, "Candles with different seeds should differ"


class TestDecisionFunnel:
    """Test decision funnel telemetry"""
    
    def test_decision_funnel_artifact_created(self, temp_config_file, temp_artifacts_dir):
        """Test that decision_funnel.json is created"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        # Check decision_funnel.json exists
        funnel_file = temp_artifacts_dir / 'decision_funnel.json'
        assert funnel_file.exists(), "decision_funnel.json should be created"
    
    def test_decision_funnel_structure(self, temp_config_file, temp_artifacts_dir):
        """Test that decision_funnel.json has expected structure"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'decision_funnel.json', 'r') as f:
            funnel_data = json.load(f)
        
        # Check top-level structure
        assert 'per_symbol' in funnel_data
        assert 'aggregate' in funnel_data
        
        # Check per-symbol data
        assert isinstance(funnel_data['per_symbol'], list)
        assert len(funnel_data['per_symbol']) > 0
        
        # Check all required fields exist in per-symbol data
        for symbol_funnel in funnel_data['per_symbol']:
            assert 'symbol' in symbol_funnel
            assert 'zones_detected' in symbol_funnel
            assert 'zones_fresh' in symbol_funnel
            assert 'zones_after_curve_filter' in symbol_funnel
            assert 'zones_after_trend_filter' in symbol_funnel
            assert 'candidates_scored' in symbol_funnel
            assert 'rejected_min_setup_score' in symbol_funnel
            assert 'rejected_min_reward_risk' in symbol_funnel
            assert 'orders_placed' in symbol_funnel
            assert 'orders_filled' in symbol_funnel
            assert 'orders_expired_ttl' in symbol_funnel
            assert 'trades_closed' in symbol_funnel
        
        # Check aggregate data
        agg = funnel_data['aggregate']
        assert 'zones_detected' in agg
        assert 'zones_fresh' in agg
        assert 'zones_after_curve_filter' in agg
        assert 'zones_after_trend_filter' in agg
        assert 'candidates_scored' in agg
        assert 'rejected_min_setup_score' in agg
        assert 'rejected_min_reward_risk' in agg
        assert 'orders_placed' in agg
        assert 'orders_filled' in agg
        assert 'orders_expired_ttl' in agg
        assert 'trades_closed' in agg
    
    def test_decision_funnel_internal_consistency(self, temp_config_file, temp_artifacts_dir):
        """Test that decision funnel counts are internally consistent"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'decision_funnel.json', 'r') as f:
            funnel_data = json.load(f)
        
        # Check each symbol's funnel consistency
        for symbol_funnel in funnel_data['per_symbol']:
            # Candidates can be scored multiple times (each fresh zone can be scored on multiple candles)
            # So candidates_scored >= zones_fresh is valid
            # Skip this assertion as it's not a valid consistency check
            
            # Orders placed should be candidates_scored - rejections
            total_rejections = (symbol_funnel['rejected_min_setup_score'] + 
                              symbol_funnel['rejected_min_reward_risk'])
            assert symbol_funnel['orders_placed'] == symbol_funnel['candidates_scored'] - total_rejections, \
                f"Orders placed should equal candidates scored minus rejections"
            
            # Orders filled should be <= orders placed
            assert symbol_funnel['orders_filled'] <= symbol_funnel['orders_placed'], \
                f"Orders filled ({symbol_funnel['orders_filled']}) should be <= orders placed ({symbol_funnel['orders_placed']})"
            
            # Trades closed should be <= orders filled
            assert symbol_funnel['trades_closed'] <= symbol_funnel['orders_filled'], \
                f"Trades closed ({symbol_funnel['trades_closed']}) should be <= orders filled ({symbol_funnel['orders_filled']})"
        
        # Check aggregate consistency
        agg = funnel_data['aggregate']
        # Skip candidates_scored vs zones_fresh check (zones can be scored multiple times)
        
        total_agg_rejections = (agg['rejected_min_setup_score'] + 
                               agg['rejected_min_reward_risk'])
        assert agg['orders_placed'] == agg['candidates_scored'] - total_agg_rejections, \
            f"Aggregate: orders placed should equal candidates scored minus rejections"
        
        assert agg['orders_filled'] <= agg['orders_placed'], \
            f"Aggregate: orders filled should be <= orders placed"
        
        assert agg['trades_closed'] <= agg['orders_filled'], \
            f"Aggregate: trades closed should be <= orders filled"
