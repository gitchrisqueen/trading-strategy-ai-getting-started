"""Supply & Demand V1 Runner - Backward Compatibility Wrapper

This module provides backward compatibility by re-exporting functions from
csv_backtest_adapter.py. It ensures that existing scripts and tests continue
to work without modification.

The actual implementation has been moved to csv_backtest_adapter.py to clarify
that it represents one of two execution paths:
1. CSV backtest adapter (this module) - for experiments and artifact generation
2. Upstream adapter (decide_trades_adapter.py) - for TradingStrategy.ai framework

Usage:
    from strategies.supply_demand_v1.runner import run_backtest_experiment
    
    # This will call csv_backtest_adapter.run_backtest_experiment()
    result = run_backtest_experiment("experiments/sd_v1_default.yaml")
"""

# Re-export everything from csv_backtest_adapter for backward compatibility
from .csv_backtest_adapter import *

# Explicit re-exports for clarity (helps IDEs and static analysis)
from .csv_backtest_adapter import (
    # Main functions
    run_backtest_experiment,
    execute_backtest_for_symbol,
    run_backtests_parallel,
    write_artifacts,
    create_artifacts_folder,
    load_config,
    
    # Data generation
    generate_synthetic_candles_mtf,
    
    # Utilities
    get_git_info,
    check_metrics_consistency,
    enum_to_string,
    
    # Data classes
    ExperimentResult,
    SymbolResult,
    OrderRecord,
    DecisionFunnel,
)

__all__ = [
    # Main functions
    'run_backtest_experiment',
    'execute_backtest_for_symbol',
    'run_backtests_parallel',
    'write_artifacts',
    'create_artifacts_folder',
    'load_config',
    # Data generation
    'generate_synthetic_candles_mtf',
    # Utilities
    'get_git_info',
    'check_metrics_consistency',
    'enum_to_string',
    # Data classes
    'ExperimentResult',
    'SymbolResult',
    'OrderRecord',
    'DecisionFunnel',
]
