"""Tests for runner integration with historical data

Tests cover:
- Config-driven data source selection
- Historical data loading in experiments
- Provenance metadata in run_manifest
- is_synthetic_data flag accuracy
"""

import pytest
import tempfile
import yaml
from pathlib import Path

from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    load_candles_from_config,
)

from strategies.supply_demand_v1.data_loader import (
    generate_sample_historical_data,
    HistoricalDataError,
)


class TestLoadCandlesFromConfig:
    """Test candle loading based on config"""
    
    @pytest.fixture
    def synthetic_config(self):
        """Config for synthetic data"""
        return {
            'data_source': 'synthetic',
            'data_generation': {
                'num_candles': 200,
                'volatility': 0.02,
                'seed': 42,
            },
            'timeframes': {
                'ltf': '15m',
            },
        }
    
    @pytest.fixture
    def historical_config(self):
        """Config for historical data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Generate sample data
            generate_sample_historical_data(
                data_dir,
                ['TESTUSDT'],
                timeframe='15m',
                num_candles=500,
            )
            
            yield {
                'data_source': 'historical',
                'historical_data': {
                    'exchange': 'binance',
                    'market_type': 'futures',
                    'data_dir': str(data_dir),
                },
                'timeframes': {
                    'ltf': '15m',
                },
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
            }
    
    def test_load_synthetic_candles(self, synthetic_config):
        """Test loading synthetic candles"""
        candles = load_candles_from_config('BTCUSDT', synthetic_config)
        
        assert len(candles) == 200
        assert all('open' in c for c in candles)
        assert all('close' in c for c in candles)
        assert all('timestamp' in c for c in candles)
    
    def test_load_historical_candles(self, historical_config):
        """Test loading historical candles"""
        candles = load_candles_from_config('TESTUSDT', historical_config)
        
        assert len(candles) > 0
        assert all('open' in c for c in candles)
        assert all('close' in c for c in candles)
        assert all('timestamp' in c for c in candles)
        assert all('symbol' in c for c in candles)
    
    def test_default_to_synthetic(self):
        """Test defaults to synthetic when data_source not specified"""
        config = {
            'data_generation': {
                'num_candles': 100,
                'volatility': 0.02,
                'seed': 42,
            },
            'timeframes': {
                'ltf': '15m',
            },
        }
        
        candles = load_candles_from_config('BTCUSDT', config)
        
        assert len(candles) == 100
    
    def test_invalid_data_source(self, synthetic_config):
        """Test error on invalid data_source"""
        synthetic_config['data_source'] = 'invalid'
        
        with pytest.raises(ValueError, match="Invalid data_source"):
            load_candles_from_config('BTCUSDT', synthetic_config)
    
    def test_historical_missing_config_section(self):
        """Test error when historical_data section missing"""
        config = {
            'data_source': 'historical',
            'timeframes': {
                'ltf': '15m',
            },
        }
        
        with pytest.raises(ValueError, match="historical_data.*section is missing"):
            load_candles_from_config('BTCUSDT', config)
    
    def test_historical_file_not_found(self):
        """Test error when historical data file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'data_source': 'historical',
                'historical_data': {
                    'exchange': 'binance',
                    'market_type': 'futures',
                    'data_dir': tmpdir,
                },
                'timeframes': {
                    'ltf': '15m',
                },
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
            }
            
            with pytest.raises(HistoricalDataError, match="Failed to load historical data"):
                load_candles_from_config('NONEXISTENT', config)


class TestRunnerWithHistoricalData:
    """Test runner integration with historical data"""
    
    @pytest.fixture
    def minimal_config_base(self):
        """Base config structure"""
        return {
            'name': 'test_historical',
            'description': 'Test historical data integration',
            'symbols': ['TESTUSDT'],
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
        }
    
    def test_runner_with_synthetic_data(self, minimal_config_base):
        """Test runner works with synthetic data"""
        config = minimal_config_base.copy()
        config['data_source'] = 'synthetic'
        config['data_generation'] = {
            'num_candles': 200,
            'volatility': 0.02,
            'seed': 42,
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            
            # Check manifest has correct provenance
            assert result.run_manifest['data_source'] == 'synthetic'
            assert result.run_manifest['is_synthetic_data'] is True
            assert result.run_manifest['datasource_name'] == 'synthetic'
            assert result.run_manifest['exchange'] is None
            assert result.run_manifest['market_type'] is None
            assert 'data_generation' in result.run_manifest
            
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_runner_with_historical_data(self, minimal_config_base):
        """Test runner works with historical data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Generate sample historical data
            generate_sample_historical_data(
                data_dir,
                ['TESTUSDT'],
                timeframe='15m',
                num_candles=500,
            )
            
            config = minimal_config_base.copy()
            config['data_source'] = 'historical'
            config['historical_data'] = {
                'exchange': 'binance',
                'market_type': 'futures',
                'data_dir': str(data_dir),
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config, f)
                config_path = f.name
            
            try:
                result = run_backtest_experiment(config_path)
                
                # Check manifest has correct provenance
                assert result.run_manifest['data_source'] == 'historical'
                assert result.run_manifest['is_synthetic_data'] is False
                assert result.run_manifest['datasource_name'] == 'binance_futures'
                assert result.run_manifest['exchange'] == 'binance'
                assert result.run_manifest['market_type'] == 'futures'
                assert 'data_generation' not in result.run_manifest
                
                # Check per-symbol provenance
                assert 'TESTUSDT' in result.run_manifest['symbol_data_provenance']
                symbol_prov = result.run_manifest['symbol_data_provenance']['TESTUSDT']
                assert 'first_timestamp' in symbol_prov
                assert 'last_timestamp' in symbol_prov
                assert 'candle_count' in symbol_prov
                assert symbol_prov['candle_count'] > 0
                assert 'checksum' in symbol_prov
                assert len(symbol_prov['checksum']) == 32  # MD5 hash
                
            finally:
                Path(config_path).unlink(missing_ok=True)
    
    def test_runner_defaults_to_synthetic(self, minimal_config_base):
        """Test runner defaults to synthetic when data_source not specified"""
        config = minimal_config_base.copy()
        # Don't specify data_source
        config['data_generation'] = {
            'num_candles': 200,
            'volatility': 0.02,
            'seed': 42,
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            
            # Should default to synthetic
            assert result.run_manifest['is_synthetic_data'] is True
            
        finally:
            Path(config_path).unlink(missing_ok=True)
