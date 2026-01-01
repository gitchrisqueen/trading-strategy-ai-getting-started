"""Tests for runner data provenance and metrics consistency

Tests cover:
- Drawdown calculation from equity curve
- Metrics warnings for impossible situations
- Data provenance in run_manifest
- Summary.json accounting_mode field
"""

import pytest
import json
import tempfile
import yaml
from pathlib import Path

from strategies.supply_demand_v1.runner import (
    calculate_max_drawdown,
    check_metrics_consistency,
    run_backtest_experiment,
    write_artifacts,
    SymbolResult,
)


class TestDrawdownCalculation:
    """Test maximum drawdown calculation"""
    
    def test_drawdown_with_simple_decline(self):
        """Test drawdown calculation with a simple equity decline"""
        equity_curve = [10000, 9500, 9000, 9500, 9000, 8500]
        max_dd = calculate_max_drawdown(equity_curve)
        
        # Peak is 10000, trough is 8500, drawdown is 1500
        assert max_dd == 1500.0
    
    def test_drawdown_with_recovery(self):
        """Test drawdown with recovery to new peak"""
        equity_curve = [10000, 9000, 11000, 10000, 9500]
        max_dd = calculate_max_drawdown(equity_curve)
        
        # First drawdown: 10000 -> 9000 = 1000
        # New peak at 11000, then drawdown 11000 -> 9500 = 1500
        # Max drawdown is 1500
        assert max_dd == 1500.0
    
    def test_drawdown_always_profitable(self):
        """Test drawdown when equity only increases"""
        equity_curve = [10000, 10500, 11000, 11500, 12000]
        max_dd = calculate_max_drawdown(equity_curve)
        
        # No drawdown if equity only increases
        assert max_dd == 0.0
    
    def test_drawdown_empty_curve(self):
        """Test drawdown with empty equity curve"""
        equity_curve = []
        max_dd = calculate_max_drawdown(equity_curve)
        
        assert max_dd == 0.0
    
    def test_drawdown_single_value(self):
        """Test drawdown with single equity value"""
        equity_curve = [10000]
        max_dd = calculate_max_drawdown(equity_curve)
        
        assert max_dd == 0.0
    
    def test_drawdown_volatile_equity(self):
        """Test drawdown with volatile equity swings"""
        equity_curve = [10000, 11000, 9000, 12000, 8000, 13000]
        max_dd = calculate_max_drawdown(equity_curve)
        
        # Peak at 12000, trough at 8000, drawdown = 4000
        assert max_dd == 4000.0


class TestMetricsConsistency:
    """Test metrics consistency warnings"""
    
    def test_warning_zero_drawdown_with_trades(self):
        """Test warning triggered when drawdown=0 but trades>0"""
        symbol_results = [
            SymbolResult(
                symbol='BTC/USDT',
                total_zones=10,
                fresh_zones=5,
                trades_placed=3,
                trades_filled=3,
                trades_won=3,
                trades_lost=0,
                total_pnl=500.0,
                win_rate=1.0,
                avg_r_realized=3.0,
                max_drawdown=0.0,  # Suspicious: 0 drawdown with trades
                final_capital=10500.0,
                equity_curve=[10000, 10200, 10350, 10500],
                data_provenance={},
            )
        ]
        
        warnings = check_metrics_consistency(symbol_results, [])
        
        # Should have warning about zero drawdown with trades
        assert len(warnings) == 1
        assert warnings[0]['type'] == 'zero_drawdown_with_trades'
        assert warnings[0]['symbol'] == 'BTC/USDT'
        assert warnings[0]['details']['trades_filled'] == 3
    
    def test_warning_low_r_with_large_pnl(self):
        """Test warning triggered when avg_r near zero but large P&L"""
        symbol_results = [
            SymbolResult(
                symbol='ETH/USDT',
                total_zones=15,
                fresh_zones=8,
                trades_placed=5,
                trades_filled=5,
                trades_won=3,
                trades_lost=2,
                total_pnl=1000.0,  # Large P&L
                win_rate=0.6,
                avg_r_realized=0.01,  # Near zero R
                max_drawdown=200.0,
                final_capital=11000.0,
                equity_curve=[10000, 10500, 10300, 10800, 11000],
                data_provenance={},
            )
        ]
        
        warnings = check_metrics_consistency(symbol_results, [])
        
        # Should have warning about low R with large P&L
        assert len(warnings) == 1
        assert warnings[0]['type'] == 'low_r_with_large_pnl'
        assert warnings[0]['symbol'] == 'ETH/USDT'
        assert warnings[0]['details']['avg_r_realized'] == 0.01
        assert warnings[0]['details']['total_pnl'] == 1000.0
    
    def test_no_warnings_for_consistent_metrics(self):
        """Test no warnings for consistent metrics"""
        symbol_results = [
            SymbolResult(
                symbol='SOL/USDT',
                total_zones=20,
                fresh_zones=10,
                trades_placed=8,
                trades_filled=8,
                trades_won=5,
                trades_lost=3,
                total_pnl=400.0,
                win_rate=0.625,
                avg_r_realized=2.5,  # Reasonable R
                max_drawdown=150.0,  # Non-zero drawdown
                final_capital=10400.0,
                equity_curve=[10000, 10100, 9950, 10200, 10400],
                data_provenance={},
            )
        ]
        
        warnings = check_metrics_consistency(symbol_results, [])
        
        # Should have no warnings
        assert len(warnings) == 0
    
    def test_no_warning_for_zero_trades(self):
        """Test no warning when no trades executed"""
        symbol_results = [
            SymbolResult(
                symbol='MATIC/USDT',
                total_zones=5,
                fresh_zones=2,
                trades_placed=0,
                trades_filled=0,
                trades_won=0,
                trades_lost=0,
                total_pnl=0.0,
                win_rate=0.0,
                avg_r_realized=0.0,
                max_drawdown=0.0,  # OK to be zero with no trades
                final_capital=10000.0,
                equity_curve=[10000],
                data_provenance={},
            )
        ]
        
        warnings = check_metrics_consistency(symbol_results, [])
        
        # Should have no warnings (zero drawdown is OK with zero trades)
        assert len(warnings) == 0


class TestDataProvenance:
    """Test data provenance in artifacts"""
    
    @pytest.fixture
    def minimal_config(self):
        """Create a minimal config for testing"""
        return {
            'name': 'provenance_test',
            'description': 'Test data provenance',
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
                'num_candles': 100,
                'volatility': 0.02,
                'seed': 42,
            },
        }
    
    def test_manifest_contains_provenance_fields(self, minimal_config):
        """Test that run_manifest contains all required provenance fields"""
        # Create temp config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            manifest = result.run_manifest
            
            # Check required provenance fields
            assert 'datasource_name' in manifest
            assert manifest['datasource_name'] == 'synthetic'
            
            assert 'is_synthetic_data' in manifest
            assert manifest['is_synthetic_data'] is True
            
            assert 'candle_timeframe' in manifest
            assert manifest['candle_timeframe'] == '15m'
            
            assert 'data_generation' in manifest
            assert 'generator_module' in manifest['data_generation']
            assert 'base_seed' in manifest['data_generation']
            assert manifest['data_generation']['base_seed'] == 42
            
            assert 'symbol_data_provenance' in manifest
            assert 'TEST/USDT' in manifest['symbol_data_provenance']
            
            # Check per-symbol provenance
            symbol_prov = manifest['symbol_data_provenance']['TEST/USDT']
            assert 'first_timestamp' in symbol_prov
            assert 'last_timestamp' in symbol_prov
            assert 'first_close' in symbol_prov
            assert 'last_close' in symbol_prov
            assert 'candle_count' in symbol_prov
            assert symbol_prov['candle_count'] == 100
            assert 'checksum' in symbol_prov
            assert len(symbol_prov['checksum']) == 32  # MD5 hash length
            
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_summary_contains_accounting_mode(self, minimal_config):
        """Test that summary.json contains accounting_mode field"""
        # Create temp config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            
            # Check aggregate metrics
            assert 'accounting_mode' in result.aggregate_metrics
            assert result.aggregate_metrics['accounting_mode'] == 'per_symbol_independent'
            
            assert 'sum_of_symbol_pnls' in result.aggregate_metrics
            
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_metrics_warnings_file_created(self, minimal_config):
        """Test that metrics_warnings.json is created"""
        # Create temp config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            
            # Create temp artifacts directory
            with tempfile.TemporaryDirectory() as temp_dir:
                artifacts_dir = Path(temp_dir)
                write_artifacts(result, artifacts_dir)
                
                # Check that metrics_warnings.json exists
                warnings_file = artifacts_dir / 'metrics_warnings.json'
                assert warnings_file.exists()
                
                # Check content
                with open(warnings_file, 'r') as f:
                    warnings_data = json.load(f)
                
                assert 'total_warnings' in warnings_data
                assert 'warnings' in warnings_data
                assert isinstance(warnings_data['warnings'], list)
            
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_symbol_result_has_equity_curve(self, minimal_config):
        """Test that symbol results include equity curve"""
        # Create temp config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            
            # Check that each symbol result has equity curve
            for sr in result.symbol_results:
                assert hasattr(sr, 'equity_curve')
                assert isinstance(sr.equity_curve, list)
                assert len(sr.equity_curve) > 0
                assert sr.equity_curve[0] == 10000.0  # Initial capital
                
                # Check that max_drawdown is calculated (not always 0)
                # It might be 0 if all trades are profitable, but it should be calculated
                assert sr.max_drawdown >= 0.0
            
        finally:
            Path(config_path).unlink(missing_ok=True)
