# Parallel Backtest Execution Guide

This document explains how to use the parallel execution feature for running multi-symbol backtests.

## Overview

The parallel execution feature speeds up multi-symbol backtests by running symbols in parallel using Python's `multiprocessing.ProcessPoolExecutor`. This is particularly beneficial when backtesting 10+ symbols.

**Key Features:**
- Deterministic results (parallel and serial produce identical outputs)
- Configurable workers and chunk sizes
- Error handling with fail-fast option
- No race conditions (only parent process writes artifacts)
- Compatible with Linux, macOS, and GitHub Codespaces

## Performance

**Benchmark** (15 symbols, 2000 candles each, synthetic data):
- Serial: 0.71s
- Parallel (4 workers, chunk size 3): 0.37s
- **Speedup: 1.93x**

Performance scales with:
- Number of symbols
- Symbol complexity (more candles = more benefit)
- Available CPU cores
- Data loading time

## Usage

### Method 1: CLI Flags (Recommended)

Enable parallel execution with command-line flags:

```bash
# Auto-detect workers (CPU count - 1)
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel

# Custom workers and chunk size
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel --workers 4 --chunk-size 3
```

### Method 2: Config File

Edit your experiment YAML config:

```yaml
# Add parallel section to your config
parallel:
  enabled: true
  workers: 4       # Number of worker processes
  chunk_size: 3    # Symbols per chunk
  fail_fast: true  # Stop on first error
```

Then run normally:

```bash
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml
```

## Configuration Parameters

### `enabled` (boolean)
- **Default:** `false`
- **Description:** Enable/disable parallel execution
- **Recommendation:** Enable for 10+ symbols

### `workers` (integer)
- **Default:** `os.cpu_count() - 1` (auto-detect)
- **Range:** 1 to CPU count
- **Description:** Number of worker processes
- **Recommendation:**
  - **GitHub Codespaces:** 2-4 workers (typical 2-4 core VMs)
  - **Local macOS:** 4-8 workers (typical 8-16 core machines)
  - **High-core servers:** Up to CPU count - 1

### `chunk_size` (integer)
- **Default:** `2`
- **Range:** 1 to number of symbols
- **Description:** Number of symbols processed per worker chunk
- **Recommendation:**
  - Small chunk (1-2): Better load balancing, more overhead
  - Large chunk (3-5): Less overhead, may be unbalanced
  - **For 10-20 symbols:** chunk_size = 2-3
  - **For 20+ symbols:** chunk_size = 3-5

### `fail_fast` (boolean)
- **Default:** `true`
- **Description:** Stop execution on first error
- **Recommendation:**
  - `true`: Development and testing (fail quickly)
  - `false`: Production runs (collect all errors)

## Examples

### Example 1: Quick Test (5 symbols)
```bash
# Serial is fine for small tests
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
```

### Example 2: Medium Run (15 symbols)
```bash
# Parallel with default settings
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel
```

### Example 3: Large Run (50+ symbols)
```bash
# Parallel with custom settings
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_large.yaml --parallel --workers 8 --chunk-size 5
```

### Example 4: GitHub Codespaces
```bash
# Conservative settings for cloud environments
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_wide_symbols.yaml --parallel --workers 2 --chunk-size 2
```

## How It Works

### Architecture

1. **Main Process:**
   - Loads config
   - Splits symbols into chunks
   - Spawns worker processes
   - Aggregates results
   - Writes artifacts (single process, no race conditions)

2. **Worker Processes:**
   - Each worker receives a chunk of symbols
   - Loads data independently (no shared DataFrames)
   - Runs backtest for each symbol in chunk
   - Returns results to main process

3. **Chunking:**
   - Reduces per-process startup overhead
   - Better CPU utilization
   - Example: 15 symbols, chunk_size=3 → 5 chunks

### Data Loading

Each worker loads its own data independently:
- **Synthetic data:** Generated with symbol-specific seeds
- **Historical data:** Loaded from CSV files per symbol
- **No pickle overhead:** Large DataFrames not passed between processes

### Determinism

Results are identical between serial and parallel:
- Symbol-specific random seeds (synthetic data)
- Deterministic sorting (by symbol, then by index)
- Independent per-symbol execution (no shared state)

## Troubleshooting

### Issue: Parallel slower than serial

**Causes:**
- Too many workers for available cores
- Small chunks increase overhead
- Fast backtests (< 1s) don't benefit much

**Solutions:**
- Reduce workers to CPU count - 1
- Increase chunk_size
- Use serial mode for quick tests

### Issue: Out of memory

**Causes:**
- Too many workers
- Large historical datasets
- Each worker loads its own data

**Solutions:**
- Reduce workers
- Reduce symbols per experiment
- Use smaller date ranges

### Issue: Different results between serial and parallel

**Causes:**
- Non-deterministic data generation
- Shared state mutation
- Race conditions

**Solutions:**
- This should NOT happen (report as bug)
- Verify with test: `pytest tests/test_runner_parallel.py::test_serial_vs_parallel_equivalence`

### Issue: Worker process crashes

**Causes:**
- Missing dependencies in worker
- Data loading errors
- Strategy bugs

**Solutions:**
- Check error messages in output
- Set `fail_fast: false` to see all errors
- Run single symbol in serial mode to debug

## Testing

Run parallel execution tests:

```bash
# All parallel tests
python -m pytest tests/test_runner_parallel.py -v

# Serial vs parallel equivalence test
python -m pytest tests/test_runner_parallel.py::test_serial_vs_parallel_equivalence -v

# Performance test
python -m pytest tests/test_runner_parallel.py::test_parallel_experiment_vs_serial_full_equivalence -v
```

## Recommended Settings

### GitHub Codespaces (2-core VM)
```yaml
parallel:
  enabled: true
  workers: 2
  chunk_size: 2
```

### GitHub Codespaces (4-core VM)
```yaml
parallel:
  enabled: true
  workers: 3
  chunk_size: 3
```

### Local Development (8-core machine)
```yaml
parallel:
  enabled: true
  workers: 6
  chunk_size: 3
```

### Production Server (16+ cores)
```yaml
parallel:
  enabled: true
  workers: 12
  chunk_size: 4
```

## Artifacts

Parallel execution preserves all artifacts:
- `summary.json` - Aggregate metrics (sorted by symbol)
- `trades.csv` - All trades (sorted by symbol, then entry_idx)
- `zones.csv` - All zones (sorted by symbol, then created_at)
- `run_manifest.json` - Run metadata
- `violations.json` - Integrity violations
- `decision_funnel.json` - Per-symbol decision funnel

All artifacts are identical to serial mode.

## Implementation Details

### Files Modified
- `strategies/supply_demand_v1/runner.py` - Core parallel execution logic
- `scripts/run_supply_demand_v1.py` - CLI flags for parallel mode
- `experiments/sd_v1_wide_symbols.yaml` - Example parallel config

### Key Functions
- `run_symbol_backtest()` - Pure function for single symbol (pickle-safe)
- `run_chunk()` - Process chunk of symbols in worker
- `run_backtests_parallel()` - Orchestrate ProcessPoolExecutor
- `run_backtest_experiment()` - Main entry point (supports both modes)

### Tests
- `tests/test_runner_parallel.py` - Comprehensive parallel execution tests
  - Serial vs parallel equivalence
  - Deterministic ordering
  - Chunk size variations
  - Full experiment integration
  - Multiprocessing compatibility

## FAQ

**Q: Should I always use parallel mode?**
A: No. Use parallel for 10+ symbols. Serial is simpler for small tests.

**Q: Can I use parallel mode with historical data?**
A: Yes! Each worker loads its own historical data independently.

**Q: Will parallel mode use more memory?**
A: Yes, each worker loads data independently. Monitor memory usage.

**Q: Can I run multiple experiments in parallel?**
A: Yes, each experiment is independent. Use separate terminal sessions.

**Q: What if one symbol fails?**
A: With `fail_fast: true`, execution stops. With `fail_fast: false`, errors are collected and other symbols continue.

**Q: Are results deterministic?**
A: Yes! Serial and parallel produce identical results (verified by tests).

**Q: Can I use this in CI/CD?**
A: Yes! Parallel mode works in GitHub Actions and other CI environments.
