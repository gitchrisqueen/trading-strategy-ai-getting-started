# Copilot Workflow Guidelines

This document defines the development workflow for future PRs and GitHub Copilot tasks.

## Before Starting Any PR

### 1. Read Context Documentation

**Always start by reading these docs** to understand the project:

1. `docs/PROJECT_CONTEXT.md` - Project overview, setup, and key locations
2. `docs/REPO_MAP.md` - Repository structure and file organization

**For Supply & Demand V1 work**:
3. `docs/STRATEGY_SUPPLY_DEMAND_V1.md` - Complete strategy specification

**Why**: These docs provide the "context pack" that prevents rediscovering project structure and strategy details every time.

### 2. Understand the Issue

- Read the issue description thoroughly
- Identify affected files and modules
- Check if tests exist for the area you're modifying
- Look for related issues or PRs

### 3. Explore the Codebase

- Review the specific files you'll be modifying
- Understand existing patterns and conventions
- Check test files to understand expected behavior
- Run existing tests to establish baseline

## PR Development Workflow

### Phase 1: Planning

1. **Create a plan** as a checklist in your first progress report
2. **Keep changes minimal** - focus on exactly what the issue requests
3. **Identify test requirements** - what tests need to be added/updated?
4. **Consider documentation** - does this change require doc updates?

### Phase 2: Implementation

1. **Make small, incremental changes**
   - One logical change at a time
   - Commit after each verified change
   - Use `report_progress` tool frequently

2. **Follow existing patterns**
   - Match code style of surrounding code
   - Use existing conventions (imports, naming, structure)
   - Don't introduce new patterns without justification

3. **Test as you go**
   - Run focused tests after each change
   - Don't wait until the end to test
   - Fix failures immediately

4. **Document your changes**
   - Update docstrings if behavior changes
   - Add comments for complex logic (only if necessary)
   - Update relevant .md files if behavior changes

### Phase 3: Validation

1. **Run the test suite**
   ```bash
   poetry run pytest
   ```

2. **Run specific test files**
   ```bash
   poetry run pytest tests/test_supply_demand_zones.py
   poetry run pytest tests/test_supply_demand_strategy.py -v
   ```

3. **Run notebooks if affected**
   ```bash
   python run_notebooks.py
   # Or manually test specific notebook
   ```

4. **Verify documentation**
   - Check that paths in docs are still accurate
   - Verify code examples still work
   - Update examples if behavior changed

### Phase 4: Review and Finalization

1. **Self-review your changes**
   - Read through all modified files
   - Check for unintended changes
   - Remove debug code, print statements, temporary files

2. **Update documentation**
   - If strategy behavior changed: update `docs/STRATEGY_SUPPLY_DEMAND_V1.md`
   - If new files added: update `docs/REPO_MAP.md`
   - If setup changed: update `docs/PROJECT_CONTEXT.md`

3. **Final test run**
   ```bash
   poetry run pytest
   ```

4. **Commit and push**
   - Use `report_progress` with descriptive commit message
   - Update PR checklist to show completion

## Code Style Guidelines

### Python Style

- **Line length**: 999 characters (Black/isort configured)
- **Imports**: Use `isort` style, absolute imports preferred
- **Formatting**: Black-compatible
- **Linting**: flake8 (ignores E203)

### Comments

- **Don't over-comment** - code should be self-documenting
- **Add comments for**:
  - Complex algorithms that aren't obvious
  - Business logic that has non-obvious constraints
  - TODOs for future enhancements
- **Match existing style** - if file has no comments, don't add them

### Module Imports

**In notebooks**:
```python
import sys
import os

# Add repo root to path
repo_root = os.path.abspath("..")
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import from package path
from strategies.supply_demand_v1.strategy import (
    SupplyDemandParameters,
    detect_zones_dbr_rbd,
)
```

**In tests**:
```python
from strategies.supply_demand_v1.strategy import (
    identify_boring_candles,
    detect_zones_dbr_rbd,
)
```

**In modules**:
```python
# Use relative imports within the same package
from .strategy import SupplyDemandParameters
from .integrity import run_integrity_checks

# Use absolute imports for cross-package
from strategies.supply_demand_v1.strategy import Zone
```

### Testing Conventions

1. **Deterministic tests**: No randomness in core logic tests
2. **Descriptive test names**: `test_boring_candle_small_body()` not `test_1()`
3. **Arrange-Act-Assert pattern**:
   ```python
   def test_zone_detection():
       # Arrange
       candles = [...]
       params = SupplyDemandParameters()
       
       # Act
       zones = detect_zones_dbr_rbd(candles, params)
       
       # Assert
       assert len(zones) == 1
       assert zones[0].zone_type == ZoneType.DEMAND
   ```
4. **Use fixtures** for common test data
5. **Test edge cases**: zero, negative, boundary conditions

## PR Size and Scope

### Keep PRs Small

- **One feature or fix per PR**
- **Aim for < 500 lines changed** (excluding generated files)
- **Break large features into multiple PRs**

### What Makes a Good PR

✅ **Good PR examples**:
- Add scoring for a new odds enhancer
- Fix a bug in zone detection logic
- Add tests for missing coverage
- Update documentation for clarity

❌ **Bad PR examples**:
- Refactor entire codebase + add feature + update docs
- Fix multiple unrelated bugs
- Add feature + change testing framework + update CI

### PR Description Checklist

Include in every PR description:

- [ ] What problem does this solve?
- [ ] What changes were made?
- [ ] How was it tested?
- [ ] Does this require documentation updates?
- [ ] Are there breaking changes?
- [ ] Are there remaining TODOs?

## Testing Requirements

### Test Coverage Expectations

**For new functions**:
- Add at least 3 tests: happy path, edge case, error case

**For bug fixes**:
- Add test that reproduces the bug (should fail before fix)
- Verify test passes after fix

**For strategy changes**:
- Update existing tests if behavior changed
- Add tests for new behavior
- Verify backtest still runs

### Running Tests

```bash
# All tests
poetry run pytest

# Specific file
poetry run pytest tests/test_supply_demand_zones.py

# Specific test
poetry run pytest tests/test_supply_demand_zones.py::TestDBRDetection::test_simple_dbr_detection

# Verbose output
poetry run pytest -v

# With coverage
poetry run pytest --cov=strategies
```

### Notebook Testing

Notebooks in `notebooks/single-backtest/` are parametrized and tested:

```bash
poetry run pytest tests/test_notebooks.py
```

**Skip notebook tests** with pragmas in notebook cells:
```python
# @ts skip-test
# This cell is skipped in automated tests

# @ts skip-test-ci
# This cell is skipped in CI but runs locally
```

## Documentation Update Rules

### When to Update Docs

**Always update docs if**:
- You add new strategy parameters
- You change strategy behavior
- You add new files or modules
- You change setup/installation steps
- You modify key algorithms

**Update these files**:

| Change Type | File to Update |
|-------------|----------------|
| New parameters or strategy logic | `docs/STRATEGY_SUPPLY_DEMAND_V1.md` |
| New files or moved files | `docs/REPO_MAP.md` |
| Setup/installation changes | `docs/PROJECT_CONTEXT.md` |
| Workflow changes | `docs/COPILOT_WORKFLOW.md` (this file) |
| Strategy spec changes | `strategies/supply_demand_v1/TradingStrategySpec.md` |

### Doc Writing Style

- **Use bullet points and tables** for clarity
- **Include code examples** for complex concepts
- **Be concise but complete** - no fluff
- **Use pseudocode** for algorithms, not full code
- **Keep paths accurate** - verify all paths exist

## Common Tasks

### Adding a New Odds Enhancer

1. Update `odds_enhancer_score()` in `strategies/supply_demand_v1/strategy.py`
2. Add parameters to `SupplyDemandParameters` if needed
3. Add tests in `tests/test_supply_demand_strategy.py`
4. Update scoring section in `docs/STRATEGY_SUPPLY_DEMAND_V1.md`
5. Run tests and notebook to verify

### Fixing a Bug

1. Write a test that reproduces the bug (should fail)
2. Fix the bug with minimal changes
3. Verify test passes
4. Check for similar bugs elsewhere
5. Update docs if behavior changed

### Adding a New Parameter

1. Add to `SupplyDemandParameters` dataclass with default value
2. Document the parameter with a comment
3. Use parameter in relevant function
4. Add test that uses the parameter
5. Update parameter table in `docs/STRATEGY_SUPPLY_DEMAND_V1.md`
6. Update notebook cell with parameter examples

### Refactoring Code

1. Ensure comprehensive test coverage exists first
2. Make refactoring in small steps
3. Run tests after each step
4. Don't change behavior - only structure
5. Update docs if public API changed

## PR Acceptance Checklist

Before marking a PR as ready for review:

- [ ] All tests pass (`poetry run pytest`)
- [ ] Code follows existing style and conventions
- [ ] Changes are minimal and focused on the issue
- [ ] Documentation updated (if needed)
- [ ] No unintended changes (debug code, temp files)
- [ ] Commit messages are clear and descriptive
- [ ] No merge conflicts
- [ ] Notebook still runs (if affected)
- [ ] Context docs (`docs/PROJECT_CONTEXT.md`, `docs/REPO_MAP.md`) read at start
- [ ] Self-reviewed all changes

## Git Workflow

### Commit Messages

Use clear, imperative commit messages:

✅ **Good**:
- "Add freshness scoring to odds enhancers"
- "Fix zone detection for edge case with single candle base"
- "Update STRATEGY_SUPPLY_DEMAND_V1.md with new parameters"

❌ **Bad**:
- "Update file"
- "Fix bug"
- "Changes"

### Using `report_progress`

Use the `report_progress` tool to:
- Commit and push changes
- Update PR description with progress
- Track checklist completion

**Example**:
```python
report_progress(
    commitMessage="Add time in base odds enhancer",
    prDescription="""
    ## Supply & Demand V1: Add Time in Base Scoring
    
    - [x] Add base_time_best and base_time_good parameters
    - [x] Implement scoring logic in odds_enhancer_score()
    - [x] Add tests for base time scoring
    - [ ] Update documentation
    - [ ] Final test run
    """
)
```

## Avoiding Common Mistakes

### ❌ Don't

- **Don't make unrelated changes** - stay focused on the issue
- **Don't remove working tests** - update them instead
- **Don't change line endings** or reformat entire files
- **Don't add new dependencies** without strong justification
- **Don't hardcode values** - use parameters instead
- **Don't ignore test failures** - fix them immediately
- **Don't skip documentation** - it's as important as code

### ✅ Do

- **Do make minimal changes** - only what's necessary
- **Do test incrementally** - don't wait until the end
- **Do follow existing patterns** - consistency matters
- **Do update docs** when behavior changes
- **Do use descriptive names** for variables and functions
- **Do handle edge cases** - think about zero, negative, boundary values
- **Do clean up** before committing - no debug code or temp files

## Getting Help

### If You're Stuck

1. **Read the context docs again** - the answer might be there
2. **Look at existing tests** - they show how the code is supposed to work
3. **Check similar code** - patterns repeat across the codebase
4. **Review related PRs** - see how similar changes were made
5. **Ask specific questions** - "How does zone freshness tracking work?" not "How does everything work?"

### Resources

- **Main README**: `README.md` - setup and examples
- **Project context**: `docs/PROJECT_CONTEXT.md` - overview
- **Repo map**: `docs/REPO_MAP.md` - file structure
- **Strategy spec**: `docs/STRATEGY_SUPPLY_DEMAND_V1.md` - complete strategy
- **Test files**: `tests/test_supply_demand_*.py` - usage examples
- **Trading Strategy docs**: https://tradingstrategy.ai/docs/

## Example PR Workflow

Here's a complete example of a good PR workflow:

### Issue: Add Volume-Based Odds Enhancer

**Step 1: Read context**
```bash
# Read these files first
docs/PROJECT_CONTEXT.md
docs/REPO_MAP.md
docs/STRATEGY_SUPPLY_DEMAND_V1.md
```

**Step 2: Create plan**
```markdown
- [ ] Add volume_threshold parameter to SupplyDemandParameters
- [ ] Update odds_enhancer_score() to include volume check
- [ ] Add tests for volume scoring
- [ ] Update STRATEGY_SUPPLY_DEMAND_V1.md with volume enhancer docs
- [ ] Run full test suite
- [ ] Test notebook with new parameter
```

**Step 3: Implementation**
```python
# 1. Add parameter
@dataclass
class SupplyDemandParameters:
    # ... existing params ...
    volume_threshold: float = 1.5  # Above average volume = 1 point

# 2. Update scoring
def odds_enhancer_score(zone, ...):
    score = 0
    # ... existing scoring ...
    
    # Volume enhancer
    if zone.legout_volume > avg_volume * params.volume_threshold:
        score += 1
    
    return score

# 3. Add tests
def test_volume_enhancer_scoring():
    # Arrange
    zone = create_test_zone(legout_volume=1000)
    avg_volume = 500
    params = SupplyDemandParameters(volume_threshold=1.5)
    
    # Act
    score = volume_score(zone, avg_volume, params)
    
    # Assert
    assert score == 1  # Volume is 2x average
```

**Step 4: Testing**
```bash
# Run specific tests
poetry run pytest tests/test_supply_demand_strategy.py::test_volume_enhancer_scoring -v

# Run full suite
poetry run pytest

# Test notebook
python run_notebooks.py
```

**Step 5: Documentation**
```markdown
# Update docs/STRATEGY_SUPPLY_DEMAND_V1.md
### 5. Volume (0 / 1 point)

Leg-out volume compared to average volume.

| Volume | Score |
|--------|-------|
| ≥ 1.5x avg | 1.0 |
| < 1.5x avg | 0.0 |

Parameter: `volume_threshold` (default 1.5)
```

**Step 6: Final review and commit**
```bash
# Self-review
git diff

# Commit
report_progress(
    commitMessage="Add volume-based odds enhancer",
    prDescription="..."
)
```

## Summary

**Remember**:
1. **Read docs first** - save time by not rediscovering
2. **Keep PRs small** - one feature, focused changes
3. **Test continuously** - don't wait until the end
4. **Update docs** - when behavior changes
5. **Follow patterns** - consistency is key
6. **Use report_progress** - commit early and often

**The goal**: Make high-quality, maintainable changes that are easy to review and won't break existing functionality.
