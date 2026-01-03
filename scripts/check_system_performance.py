#!/usr/bin/env python3
"""System Performance Check for Supply & Demand V1 Strategy

This script checks your system's performance and provides recommendations
for optimizing backtest execution speed.

Usage:
    python scripts/check_system_performance.py
"""

import sys
import platform
import time
import os
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

try:
    from strategies.supply_demand_v1.runner import generate_synthetic_candles, execute_backtest_for_symbol
    from strategies.supply_demand_v1.strategy import SupplyDemandParameters
except ImportError as e:
    print(f"Error importing strategy modules: {e}")
    print("Make sure you're running this script from the repository root.")
    sys.exit(1)


def check_python_version():
    """Check Python version"""
    version = sys.version_info
    print("=" * 80)
    print("PYTHON VERSION")
    print("=" * 80)
    print(f"Version: {version.major}.{version.minor}.{version.micro}")
    print(f"Implementation: {platform.python_implementation()}")
    
    if version.major == 3 and version.minor in [11, 12]:
        print("✓ Python version is supported")
        return True
    else:
        print(f"⚠ Warning: Python {version.major}.{version.minor} may not be optimal")
        print("  Recommended: Python 3.11 or 3.12")
        return False


def check_system_info():
    """Display system information"""
    print("\n" + "=" * 80)
    print("SYSTEM INFORMATION")
    print("=" * 80)
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Processor: {platform.processor()}")
    
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False)
        cpu_count_logical = psutil.cpu_count(logical=True)
        memory = psutil.virtual_memory()
        
        print(f"CPU Cores: {cpu_count} physical, {cpu_count_logical} logical")
        print(f"Total RAM: {memory.total / (1024**3):.1f} GB")
        print(f"Available RAM: {memory.available / (1024**3):.1f} GB")
        
        if cpu_count >= 4:
            print("✓ CPU core count is good for parallel processing (future)")
        
        if memory.total >= 8 * (1024**3):
            print("✓ RAM is sufficient for large backtests")
        elif memory.total >= 2 * (1024**3):
            print("⚠ RAM is adequate for small-medium backtests")
        else:
            print("⚠ Low RAM may limit backtest size")
            
    except ImportError:
        print("\nNote: Install 'psutil' for detailed system info:")
        print("  pip install psutil")


def benchmark_performance():
    """Run performance benchmark"""
    print("\n" + "=" * 80)
    print("PERFORMANCE BENCHMARK")
    print("=" * 80)
    
    # Test 1: Small dataset (1000 candles)
    print("\nTest 1: Small dataset (1,000 candles, 1 symbol)")
    params = SupplyDemandParameters()
    candles = generate_synthetic_candles('TEST/USDT', 1000, seed=42)
    
    start = time.time()
    trades, zones, final_capital, equity_curve, funnel = execute_backtest_for_symbol(
        'TEST/USDT', candles, params, 10000.0
    )
    elapsed = time.time() - start
    
    print(f"  Runtime: {elapsed:.3f}s")
    print(f"  Zones detected: {len(zones)}")
    print(f"  Trades filled: {len([t for t in trades if t['realized_R'] is not None])}")
    
    if elapsed < 0.1:
        print("  ✓ Excellent performance!")
    elif elapsed < 0.5:
        print("  ✓ Good performance")
    else:
        print("  ⚠ Performance may be suboptimal")
    
    # Test 2: Medium dataset (5000 candles)
    print("\nTest 2: Medium dataset (5,000 candles, 1 symbol)")
    candles = generate_synthetic_candles('TEST/USDT', 5000, seed=42)
    
    start = time.time()
    trades, zones, final_capital, equity_curve, funnel = execute_backtest_for_symbol(
        'TEST/USDT', candles, params, 10000.0
    )
    elapsed = time.time() - start
    
    print(f"  Runtime: {elapsed:.3f}s")
    print(f"  Zones detected: {len(zones)}")
    print(f"  Trades filled: {len([t for t in trades if t['realized_R'] is not None])}")
    
    if elapsed < 0.5:
        print("  ✓ Excellent performance!")
    elif elapsed < 2.0:
        print("  ✓ Good performance")
    else:
        print("  ⚠ Performance may be suboptimal")
    
    # Test 3: Large dataset (35000 candles)
    print("\nTest 3: Large dataset (35,000 candles, 1 symbol)")
    print("  (This will take ~45-60 seconds...)")
    candles = generate_synthetic_candles('TEST/USDT', 35000, seed=42)
    
    start = time.time()
    trades, zones, final_capital, equity_curve, funnel = execute_backtest_for_symbol(
        'TEST/USDT', candles, params, 10000.0
    )
    elapsed = time.time() - start
    
    print(f"  Runtime: {elapsed:.3f}s")
    print(f"  Zones detected: {len(zones)}")
    print(f"  Trades filled: {len([t for t in trades if t['realized_R'] is not None])}")
    
    if elapsed < 60:
        print("  ✓ Excellent performance!")
    elif elapsed < 120:
        print("  ✓ Good performance")
    else:
        print("  ⚠ Performance may be suboptimal")
    
    return elapsed


def provide_recommendations(benchmark_time):
    """Provide optimization recommendations"""
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if benchmark_time < 60:
        print("\n✓ Your system performs well for typical backtests!")
        print("\nOptional optimizations:")
        print("  1. Use Python optimization flag: python -O scripts/run_supply_demand_v1.py")
        print("  2. Close unnecessary background applications")
        print("  3. Use synthetic data for development (faster than historical)")
    else:
        print("\n⚠ Your system may benefit from optimization:")
        print("\n1. Check CPU usage during backtests:")
        print("   - Linux/Mac: htop or top")
        print("   - Windows: Task Manager")
        
        print("\n2. Ensure sufficient free RAM:")
        print("   - Close browser tabs and other applications")
        print("   - Large backtests need 4-8 GB free RAM")
        
        print("\n3. Use Python optimization flag:")
        print("   python -O scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml")
        
        print("\n4. Start with smaller datasets:")
        print("   - Use 1-2 symbols instead of 5-15")
        print("   - Use 1000-5000 candles for development")
        print("   - Scale up after confirming performance")
    
    print("\n" + "=" * 80)
    print("For detailed performance tips, see: docs/PERFORMANCE_GUIDE.md")
    print("=" * 80)


def main():
    """Run all checks"""
    print("\n" + "=" * 80)
    print("Supply & Demand V1 Strategy - System Performance Check")
    print("=" * 80)
    
    # Check Python version
    check_python_version()
    
    # Check system info
    check_system_info()
    
    # Run benchmark
    benchmark_time = benchmark_performance()
    
    # Provide recommendations
    provide_recommendations(benchmark_time)
    
    print("\n✓ Performance check complete!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Error during performance check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
