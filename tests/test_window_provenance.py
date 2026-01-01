"""Tests for explicit date-range controls, window provenance, and decision funnel

Tests cover:
- use_full_history=true uses full available data
- start_date/end_date slicing works correctly  
- run_manifest includes window provenance fields
- decision_funnel.json is created and valid
- metrics_warnings includes window utilization warnings
"""

import pytest
import json
import tempfile
import shutil
import yaml
from pathlib import Path
from datetime import datetime, timezone

from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    write_artifacts,
)
from strategies.supply_demand_v1.data_loader import (
    find_common_window,
    load_historical_candles,
    generate_sample_historical_data,
)


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory with sample historical data"""
    temp_dir = tempfile.mkdtemp()
    data_dir = Path(temp_dir)
    
    # Generate sample data for multiple timeframes
    symbols = ['TESTUSDT']
    generate_sample_historical_data(
        data_dir,
        symbols,
        timeframe='15m',
        num_candles=10000,  # ~100 days of 15m candles
        exchange='binance',
        market_type='futures'
    )
    generate_sample_historical_data(
        data_dir,
        symbols,
        timeframe='1h',
        num_candles=2500,  # ~100 days of 1h candles
        exchange='binance',
        market_type='futures'
    )
    generate_sample_historical_data(
        data_dir,
        symbols,
        timeframe='4h',
        num_candles=625,  # ~100 days of 4h candles
        exchange='binance',
        market_type='futures'
    )
    
    yield data_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def full_history_config(temp_data_dir):
    """Config with use_full_history=true"""
    return {
        'name': 'test_full_history',
        'description': 'Test full history usage',
        'data_source': 'historical',
        'use_full_history': True,
        'historical_data': {
            'exchange': 'binance',
            'market_type': 'futures',
            'data_dir': str(temp_data_dir),
        },
        'symbols': ['TESTUSDT'],
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
            'num_candles': 1000,
            'volatility': 0.02,
            'seed': 42,
        },
    }


@pytest.fixture
def sliced_window_config(temp_data_dir):
    """Config with explicit start_date/end_date"""
    config = {
        'name': 'test_sliced_window',
        'description': 'Test date range slicing',
        'data_source': 'historical',
        'use_full_history': False,
        'start_date': '2024-02-01',
        'end_date': '2024-02-29',
        'historical_data': {
            'exchange': 'binance',
            'market_type': 'futures',
            'data_dir': str(temp_data_dir),
        },
        'symbols': ['TESTUSDT'],
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
            'num_candles': 1000,
            'volatility': 0.02,
            'seed': 42,
        },
    }
    return config


@pytest.fixture
def temp_config_file(full_history_config):
    """Create temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(full_history_config, f)
        config_path = f.name
    
    yield config_path
    
    Path(config_path).unlink(missing_ok=True)


@pytest.fixture
def temp_artifacts_dir():
    """Create temporary artifacts directory"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestCommonWindow:
    """Test finding common window across multiple timeframes"""
    
    def test_find_common_window(self, temp_data_dir):
        """Test that common window is correctly identified"""
        start, end = find_common_window(
            symbol='TESTUSDT',
            timeframes=['15m', '1h', '4h'],
            data_dir=temp_data_dir,
            exchange='binance',
            market_type='futures'
        )
        
        assert start is not None
        assert end is not None
        assert start <= end
        
        # Parse as dates
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        assert start_dt < end_dt


class TestFullHistoryUsage:
    """Test use_full_history=true functionality"""
    
    def test_full_history_uses_all_available_data(self, temp_config_file, temp_artifacts_dir):
        """Test that use_full_history=true uses full available window"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        # Check that data was loaded
        assert len(result.symbol_results) == 1
        sr = result.symbol_results[0]
        
        # Check that used_count is close to available_count
        available = sr.data_provenance.get('available_count', 0)
        used = sr.data_provenance.get('used_count', 0)
        
        assert available > 0, "Should have available data"
        assert used > 0, "Should have used data"
        # With full history, used should be close to available (within reasonable tolerance)
        # Allow some difference due to timeframe alignment
        assert used >= available * 0.95, f"Used {used} should be close to available {available}"
    
    def test_run_manifest_has_window_fields(self, temp_config_file, temp_artifacts_dir):
        """Test that run_manifest includes requested_window and used_window_global"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        # Load run_manifest.json
        with open(temp_artifacts_dir / 'run_manifest.json') as f:
            manifest = json.load(f)
        
        # Check requested_window
        assert 'requested_window' in manifest
        assert 'use_full_history' in manifest['requested_window']
        assert manifest['requested_window']['use_full_history'] is True
        
        # Check used_window_global
        assert 'used_window_global' in manifest
        if manifest['used_window_global']:  # May be empty if no data
            assert 'start_ts' in manifest['used_window_global']
            assert 'end_ts' in manifest['used_window_global']


class TestDateRangeSlicing:
    """Test explicit start_date/end_date slicing"""
    
    def test_date_range_slicing_works(self, sliced_window_config, temp_artifacts_dir):
        """Test that start_date/end_date correctly slices data"""
        # Write config to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sliced_window_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            write_artifacts(result, temp_artifacts_dir)
            
            # Check that used window matches requested window
            sr = result.symbol_results[0]
            used_first = datetime.fromisoformat(sr.data_provenance['used_first_ts'])
            used_last = datetime.fromisoformat(sr.data_provenance['used_last_ts'])
            
            # Should be within the requested range (Feb 2024)
            assert used_first.year == 2024
            assert used_first.month == 2
            assert used_last.year == 2024
            assert used_last.month == 2
            
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_run_manifest_shows_requested_dates(self, sliced_window_config, temp_artifacts_dir):
        """Test that run_manifest shows requested start/end dates"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sliced_window_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            write_artifacts(result, temp_artifacts_dir)
            
            with open(temp_artifacts_dir / 'run_manifest.json') as f:
                manifest = json.load(f)
            
            # Check requested_window
            requested = manifest['requested_window']
            assert requested['start_date'] == '2024-02-01'
            assert requested['end_date'] == '2024-02-29'
            assert requested['use_full_history'] is False
            
        finally:
            Path(config_path).unlink(missing_ok=True)


class TestDecisionFunnel:
    """Test decision funnel tracking and artifact generation"""
    
    def test_decision_funnel_json_created(self, temp_config_file, temp_artifacts_dir):
        """Test that decision_funnel.json is created"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        # Check file exists
        funnel_file = temp_artifacts_dir / 'decision_funnel.json'
        assert funnel_file.exists(), "decision_funnel.json should be created"
        
        # Load and validate structure
        with open(funnel_file) as f:
            funnel_data = json.load(f)
        
        assert 'per_symbol' in funnel_data
        assert 'aggregate' in funnel_data
        
        # Check per-symbol structure
        assert len(funnel_data['per_symbol']) == 1  # One symbol in test
        symbol_funnel = funnel_data['per_symbol'][0]
        
        required_fields = [
            'symbol', 'zones_detected', 'zones_fresh', 'candidates_evaluated',
            'rejected_curve', 'rejected_trend', 'rejected_min_score', 'rejected_min_rr',
            'orders_placed', 'orders_filled', 'orders_expired_ttl'
        ]
        
        for field in required_fields:
            assert field in symbol_funnel, f"Missing field: {field}"
            assert isinstance(symbol_funnel[field], (int, str)), f"Invalid type for {field}"
        
        # Check aggregate structure
        agg = funnel_data['aggregate']
        for field in required_fields[1:]:  # Skip 'symbol'
            assert field in agg, f"Missing aggregate field: {field}"
            assert isinstance(agg[field], int), f"Invalid type for aggregate {field}"
    
    def test_funnel_counts_are_logical(self, temp_config_file, temp_artifacts_dir):
        """Test that funnel counts follow logical constraints"""
        result = run_backtest_experiment(temp_config_file)
        write_artifacts(result, temp_artifacts_dir)
        
        with open(temp_artifacts_dir / 'decision_funnel.json') as f:
            funnel_data = json.load(f)
        
        agg = funnel_data['aggregate']
        
        # Zones fresh should be <= zones detected
        assert agg['zones_fresh'] <= agg['zones_detected']
        
        # Orders filled should be <= orders placed
        assert agg['orders_filled'] <= agg['orders_placed']
        
        # Sum of rejections + orders placed should relate to candidates evaluated
        # (May not be exact due to logic flow, but should be reasonable)
        total_outcomes = (
            agg['rejected_curve'] + agg['rejected_trend'] + 
            agg['rejected_min_score'] + agg['rejected_min_rr'] + 
            agg['orders_placed']
        )
        # Total outcomes should not exceed candidates evaluated
        assert total_outcomes <= agg['candidates_evaluated'] * 2  # Allow some slack


class TestWindowUtilizationWarnings:
    """Test warnings when used < 80% of available data"""
    
    def test_low_utilization_generates_warning(self, sliced_window_config, temp_artifacts_dir):
        """Test that warning is generated when using small subset of data"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sliced_window_config, f)
            config_path = f.name
        
        try:
            result = run_backtest_experiment(config_path)
            write_artifacts(result, temp_artifacts_dir)
            
            # Load metrics_warnings.json
            with open(temp_artifacts_dir / 'metrics_warnings.json') as f:
                warnings_data = json.load(f)
            
            # Check if any warnings are about low window utilization
            low_util_warnings = [
                w for w in warnings_data['warnings']
                if w.get('type') == 'low_window_utilization'
            ]
            
            # Should have at least one warning (using only Feb 2024 of ~100 days)
            assert len(low_util_warnings) > 0, "Should warn about low utilization"
            
            # Check warning structure
            warning = low_util_warnings[0]
            assert 'symbol' in warning
            assert 'message' in warning
            assert 'details' in warning
            assert 'utilization_pct' in warning['details']
            
            # Utilization should be < 80%
            assert warning['details']['utilization_pct'] < 0.8
            
        finally:
            Path(config_path).unlink(missing_ok=True)


class TestBackwardCompatibility:
    """Test that existing configs without new fields still work"""
    
    def test_synthetic_data_without_new_fields(self):
        """Test that synthetic data configs work without use_full_history"""
        config = {
            'name': 'test_backward_compat',
            'description': 'Test backward compatibility',
            'data_source': 'synthetic',  # No use_full_history field
            'symbols': ['TEST/USDT'],
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
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            # Should run without errors
            result = run_backtest_experiment(config_path)
            assert result is not None
            assert len(result.decision_funnels) == 1
            
        finally:
            Path(config_path).unlink(missing_ok=True)
