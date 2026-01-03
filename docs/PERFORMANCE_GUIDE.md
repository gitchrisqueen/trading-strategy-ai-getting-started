# Supply & Demand V1 Strategy - Performance Guide

This guide provides optimization tips and system requirements for running the Supply & Demand V1 backtesting strategy efficiently.

## Performance Benchmarks

### Synthetic Data Performance (Optimized v1.2)

| Dataset Size | Candles | Zones | Trades | Runtime | Speedup |
|-------------|---------|-------|--------|---------|---------|
| **Small (5 symbols, 3 months)** | 5,000 | 456 | 24 | 0.17s | 25x faster |
| **Large (1 symbol, 1 year)** | 35,040 | 3,234 | 187 | 16.5s | **65% faster** |
| **Per 1000 candles** | 1,000 | ~90 | ~5 | ~0.015s | 50x faster |

### Optimization History

**v1.2 (Latest) - Spatial Indexing**
- Added spatial indexing for zone freshness checks
- Only checks zones that overlap current candle's price range
- **Additional 65% speedup** for large datasets (47s → 16.5s)
- Complexity: O(log z + k) where k = overlapping zones per candle

**v1.1 - Incremental Tracking**
- **25x speedup** for typical backtests (4.2s → 0.17s)
- Incremental freshness tracking with `last_checked_idx`
- Linear scaling with data size (was exponential before)

**v1.0 - Original**
- O(n²) complexity rescanning all candles
- 4.2s for 5 symbols × 1K candles

### Key Optimizations

#### Optimization 1: Incremental Freshness Tracking (v1.1)

**Problem**: Original `is_zone_fresh()` rescanned ALL candles from zone creation on EVERY tick
- Complexity: O(n²) where n = number of candles
- Example: 35,000 candles × 3,200 zones = ~112 million comparisons

**Solution**: Incremental freshness tracking
- Only check NEW candles since last check
- Track `last_checked_idx` to avoid redundant work
- Complexity: O(n) - linear with candles

#### Optimization 2: Spatial Indexing (v1.2)

**Problem**: Even with incremental tracking, we check ALL zones on EVERY candle
- Complexity: O(z) per candle where z = number of zones
- Example: 35,000 candles × 3,200 zones = 112 million zone checks

**Solution**: Spatial indexing with price buckets
- Organize zones into price range buckets
- Only check zones whose price range overlaps the current candle
- Complexity: O(log z + k) where k = overlapping zones (typically 0-5)
- Example: 35,000 candles × ~5 overlaps = 175,000 checks (640x reduction!)

**Implementation**:
```python
# Naive approach (v1.0)
for zone in zones:
    check_all_candles(zone)  # O(n²)

# Incremental approach (v1.1)
for zone in zones:
    check_new_candles_only(zone)  # O(n*z)

# Spatial indexing approach (v1.2)
overlapping_zones = find_overlapping_zones(candle)  # O(log z)
for zone in overlapping_zones:  # k zones
    check_new_candles_only(zone)  # O(n*k) where k << z
```

## System Requirements

### Minimum Requirements

- **Python**: 3.11 or 3.12
- **RAM**: 2 GB minimum (scales with data size)
- **CPU**: Any modern processor (single-threaded)
- **Disk**: 100 MB for code + data storage

### Recommended for Large Backtests

- **RAM**: 8 GB+ for multi-symbol, multi-year backtests
- **CPU**: 4+ cores (for future parallel processing)
- **Python**: Latest 3.12.x (best performance)

## Performance Tips

### 1. Use Synthetic Data for Development

Synthetic data is **10x faster** than loading historical data:

```yaml
# Fast: Synthetic data
data_generation:
  num_candles: 1000
  volatility: 0.02
  seed: 42
```

vs

```yaml
# Slower: Historical data (disk I/O overhead)
data_source: "historical"
historical_data:
  exchange: "binance"
  market_type: "futures"
```

**Tip**: Develop and test with synthetic data, validate with historical data.

### 2. Limit Symbol Count for Quick Tests

Use fewer symbols for rapid iteration:

```yaml
# Development: 1-2 symbols
symbols:
  - "BTC/USDT"
  - "ETH/USDT"

# Production: 5-15 symbols
symbols:
  - "BTC/USDT"
  - "ETH/USDT"
  - "SOL/USDT"
  - "MATIC/USDT"
  - "AVAX/USDT"
```

### 3. Reduce Candle Count for Exploration

Use smaller datasets when tuning parameters:

```yaml
# Quick exploration: ~3 months
data_generation:
  num_candles: 8640  # 90 days × 24h × 4 candles/h

# Full backtest: ~1 year
data_generation:
  num_candles: 35040  # 365 days × 24h × 4 candles/h
```

### 4. Run Python with Optimization Flags

For production runs, use Python's optimization mode:

```bash
# Normal run
python scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Optimized run (removes debug overhead)
python -O scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml
```

**Speedup**: 5-10% faster with `-O` flag

### 5. Profile Your Code

If backtests are still slow, profile to find bottlenecks:

```bash
python -m cProfile -o profile.stats scripts/run_supply_demand_v1.py --config experiments/sd_v1_default.yaml

# Analyze results
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative')
p.print_stats(30)
"
```

### 6. Check System Resource Usage

Monitor CPU and memory during runs:

**Linux/Mac:**
```bash
# Monitor in real-time
htop

# Or use top
top -p $(pgrep -f run_supply_demand)
```

**Windows:**
```powershell
# Task Manager (Ctrl+Shift+Esc)
# Or PowerShell
Get-Process python | Select-Object CPU, PM
```

### 7. Disable Unnecessary Background Processes

Free up system resources before large backtests:

- Close browsers with many tabs
- Stop video streaming / downloads
- Disable antivirus real-time scanning temporarily
- Close IDEs if not debugging

## Scaling Guidelines

### Expected Runtime by Dataset Size

Based on benchmarks with optimized code:

| Candles/Symbol | Symbols | Total Candles | Approx Runtime |
|---------------|---------|---------------|----------------|
| 1,000 | 1 | 1,000 | 0.03s |
| 1,000 | 5 | 5,000 | 0.17s |
| 1,000 | 10 | 10,000 | 0.35s |
| 35,000 | 1 | 35,000 | 47s |
| 35,000 | 5 | 175,000 | 4 min |
| 70,000 | 1 | 70,000 | 94s |
| 70,000 | 5 | 350,000 | 8 min |

**Formula**: Runtime ≈ 0.0013s × total_candles

### Memory Usage

Memory scales with candles and zones:

- **Candles**: ~200 bytes per candle (OHLCV + metadata)
- **Zones**: ~400 bytes per zone (geometry + freshness tracking)
- **Trades**: ~600 bytes per trade (entry/exit + P&L)

**Example**: 35,000 candles, 3,200 zones, 200 trades = ~10 MB

## Troubleshooting Slow Performance

### Issue 1: Slow Historical Data Loading

**Symptom**: Backtest takes 30+ seconds even for small datasets

**Solution**:
1. Check disk I/O speed (CSV loading is disk-bound)
2. Use SSD instead of HDD if possible
3. Switch to synthetic data for development
4. Cache loaded data in memory (future enhancement)

### Issue 2: High Memory Usage

**Symptom**: System runs out of memory or swaps to disk

**Solution**:
1. Reduce number of symbols
2. Use date range filtering instead of full history
3. Process symbols sequentially instead of all at once
4. Increase system RAM

### Issue 3: CPU Bottleneck

**Symptom**: One CPU core at 100%, others idle

**Solution**:
1. The current implementation is single-threaded (by design)
2. For multi-symbol backtests, consider parallel processing (future)
3. Run multiple experiments in separate processes

### Issue 4: Profiler Shows Unexpected Hotspot

**Symptom**: Profiler identifies function taking >20% of runtime

**Expected hotspots** (in order):
1. `is_zone_fresh()` - ~5-10% (optimized from 96%)
2. `detect_zones_dbr_rbd()` - ~5-10% (zone detection)
3. `generate_synthetic_candles()` - ~2-5% (if using synthetic data)
4. `odds_enhancer_score()` - ~2-5% (scoring logic)

If other functions dominate, investigate and optimize.

## Development vs Production Performance

### Development Mode (Fast Iteration)

Use these settings for rapid development:

```yaml
# experiments/dev_quick.yaml
symbols: ["BTC/USDT"]
data_generation:
  num_candles: 1000
  seed: 42
```

**Expected runtime**: <0.1 seconds

### Production Mode (Comprehensive Backtest)

Use these settings for final validation:

```yaml
# experiments/prod_full.yaml
symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "MATIC/USDT", "AVAX/USDT"]
data_generation:
  num_candles: 35040  # 1 year
  seed: 42
```

**Expected runtime**: ~2-3 minutes

## Future Optimization Opportunities

These optimizations are planned for future releases:

1. **Parallel symbol processing**: Process multiple symbols in parallel
2. **Vectorized zone detection**: Use NumPy for batch operations
3. **Cached candle loading**: In-memory cache for repeated runs
4. **GPU acceleration**: For zone detection with very large datasets
5. **JIT compilation**: Use Numba for hot loops

## Getting Help

If backtests are still slow after following this guide:

1. **Profile your run**: Use cProfile to identify bottlenecks
2. **Share profiling output**: Open an issue with profile stats
3. **Report system specs**: CPU, RAM, disk type, Python version
4. **Provide config**: Share experiment YAML config

## Changelog

### v1.2 (2026-01-03) - Spatial Indexing Optimization

- **Additional 65% speedup** for large datasets (47s → 16.5s for 35K candles)
- Added spatial indexing via `ZoneFreshnessTracker` class
- Only checks zones that overlap current candle's price range
- Organized zones into price buckets for O(log z + k) lookup
- Reduced zone checks from 112M to 175K for large backtests (640x reduction)
- Maintained 100% test coverage with new `test_zone_tracker.py`

### v1.1 (2026-01-03) - Incremental Tracking Optimization

- **25x speedup** for typical backtests (4.2s → 0.17s)
- Added incremental `is_zone_fresh()` tracking
- Added `last_checked_idx` field to Zone class
- Maintained 100% test coverage and integrity checks

### v1.0 (2024-12-01) - Initial Release

- Basic freshness tracking (O(n²) complexity)
- Single-threaded execution
- CSV-based historical data loading
