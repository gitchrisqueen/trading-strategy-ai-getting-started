#!/usr/bin/env python3
"""CLI wrapper for running Supply & Demand V1 experiments

Usage:
    python ./scripts/run_supply_demand_v1.py --config ./experiments/sd_v1_default.yaml
    python ./scripts/run_supply_demand_v1.py --config ./experiments/sd_v1_wide_symbols.yaml

This script:
1. Parses command-line arguments
2. Loads experiment configuration
3. Runs the backtest experiment
4. Generates artifacts in ./artifacts/sd_v1/<timestamp>_<hash>/
5. Displays summary results
"""

import argparse
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from strategies.supply_demand_v1.runner import (
    run_backtest_experiment,
    create_artifacts_folder,
    write_artifacts,
)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Run Supply & Demand V1 backtest experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run default experiment (serial mode)
  python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
  
  # Run with parallel execution
  python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel
  
  # Run parallel with custom workers and chunk size
  python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel --workers 4 --chunk-size 3

Artifacts are written to:
  ./artifacts/sd_v1/<timestamp>_<short_hash>/
  
Output files:
  - summary.json     (aggregate + per-symbol metrics)
  - trades.csv       (all trade details)
  - zones.csv        (all detected zones)
  - run_manifest.json (run metadata: git commit, config, python version)
  - violations.json  (integrity check results)
        """
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to experiment YAML configuration file'
    )
    
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Enable parallel execution (uses multiprocessing)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='Number of worker processes (default: CPU count - 1)'
    )
    
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=None,
        help='Number of symbols per chunk (default: 2)'
    )
    
    args = parser.parse_args()
    
    # Validate config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    
    # Load config and apply CLI overrides
    from strategies.supply_demand_v1.runner import load_config
    config = load_config(str(config_path))
    
    # Override parallel settings from CLI
    if args.parallel or args.workers is not None or args.chunk_size is not None:
        if 'parallel' not in config:
            config['parallel'] = {}
        
        if args.parallel:
            config['parallel']['enabled'] = True
        
        if args.workers is not None:
            config['parallel']['workers'] = args.workers
        
        if args.chunk_size is not None:
            config['parallel']['chunk_size'] = args.chunk_size
    
    print("=" * 80)
    print("Supply & Demand V1 Experiment Runner")
    print("=" * 80)
    print(f"Config: {config_path}")
    
    # Display parallel settings if enabled
    if config.get('parallel', {}).get('enabled', False):
        import os
        parallel = config['parallel']
        workers = parallel.get('workers', max(1, os.cpu_count() - 1))
        chunk_size = parallel.get('chunk_size', 2)
        print(f"Mode: PARALLEL")
        print(f"  Workers: {workers}")
        print(f"  Chunk size: {chunk_size}")
    else:
        print(f"Mode: SERIAL")
    
    print()
    
    try:
        # Run experiment
        print("Running backtest experiment...")
        result = run_backtest_experiment(config_path=str(config_path), config=config)
        
        # Create artifacts folder
        artifacts_dir = create_artifacts_folder()
        
        # Write artifacts
        write_artifacts(result, artifacts_dir)
        
        # Display summary
        print("\n" + "=" * 80)
        print("EXPERIMENT SUMMARY")
        print("=" * 80)
        print(f"Total Symbols:    {result.aggregate_metrics['total_symbols']}")
        print(f"Total Trades:     {result.aggregate_metrics['total_trades']}")
        print(f"Filled Trades:    {result.aggregate_metrics['total_filled']}")
        print(f"Won Trades:       {result.aggregate_metrics['total_won']}")
        print(f"Lost Trades:      {result.aggregate_metrics['total_lost']}")
        print(f"Win Rate:         {result.aggregate_metrics['overall_win_rate']:.2%}")
        print(f"Total P&L:        ${result.aggregate_metrics['overall_pnl']:.2f}")
        print(f"Avg R Realized:   {result.aggregate_metrics['avg_r_realized']:.2f}R")
        print()
        
        print("=" * 80)
        print("INTEGRITY CHECK")
        print("=" * 80)
        print(f"Total Trades Checked:  {result.integrity_report.total_trades}")
        print(f"Violations Found:      {len(result.integrity_report.violations)}")
        print(f"Status:                {'✓ CLEAN' if result.integrity_report.clean else '✗ VIOLATIONS'}")
        
        if result.integrity_report.violations:
            print("\nViolation Breakdown:")
            for vtype, count in result.integrity_report.violation_counts.items():
                print(f"  - {vtype.value}: {count}")
        print()
        
        print("=" * 80)
        print("PER-SYMBOL RESULTS")
        print("=" * 80)
        for sr in result.symbol_results:
            print(f"\n{sr.symbol}:")
            print(f"  Zones:        {sr.total_zones} ({sr.fresh_zones} fresh)")
            print(f"  Trades:       {sr.trades_filled} filled / {sr.trades_placed} placed")
            print(f"  Win Rate:     {sr.win_rate:.2%}")
            print(f"  P&L:          ${sr.total_pnl:.2f}")
            print(f"  Avg R:        {sr.avg_r_realized:.2f}R")
        
        print("\n" + "=" * 80)
        print(f"✓ Experiment complete!")
        print(f"✓ Artifacts: {artifacts_dir}")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error running experiment: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
