# Documentation Directory

This directory contains comprehensive documentation for the Trading Strategy AI Getting Started repository.

## Documentation Files

### Project Setup and Context

- **[PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)** - Project overview, environment setup instructions, and getting started guide
  - What this repository is for
  - How to set up your development environment
  - How to run the Supply & Demand V1 strategy notebook
  - Where key implementations live
  - Troubleshooting common issues

### Repository Structure

- **[REPO_MAP.md](./REPO_MAP.md)** - Complete map of repository structure
  - Directory layout and organization
  - Key files and their purposes
  - Import patterns for notebooks and tests
  - Developer notes on module resolution

### Development Workflow

- **[COPILOT_WORKFLOW.md](./COPILOT_WORKFLOW.md)** - Development guidelines and PR best practices
  - Pre-PR checklist
  - Code style guidelines (Python, Black, line length 999)
  - Testing conventions
  - PR size and scope recommendations
  - Common development tasks with step-by-step guides
  - Git workflow and commit standards

### Trading Strategies

For detailed strategy documentation, see the individual strategy folders:

- **[Supply & Demand V1 Strategy](../strategies/supply_demand_v1/README.md)** - Complete specification and implementation guide
  - Strategy overview and core concepts
  - Candle classification rules
  - Zone detection patterns (DBR/RBD)
  - Multi-timeframe analysis (HTF/ITF/LTF)
  - Scoring system and odds enhancers
  - Entry/stop/target rules
  - Trade management and position sizing
  - Complete workflow with pseudocode
  - How to run backtests
  - Parameter reference

### Legacy Documentation

- **[TradingStrategySpec.md](./TradingStrategySpec.md)** - Original trading strategy specification

## Quick Start

**New to this repository?**

1. Start with [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) to understand what this repository is and how to set up your environment
2. Review [REPO_MAP.md](./REPO_MAP.md) to understand the repository structure
3. Read the [Supply & Demand V1 Strategy documentation](../strategies/supply_demand_v1/README.md) to understand the example strategy
4. Check [COPILOT_WORKFLOW.md](./COPILOT_WORKFLOW.md) before contributing

**Want to run a backtest?**

- See [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) for quick start instructions
- See [Supply & Demand V1 README](../strategies/supply_demand_v1/README.md) for strategy-specific details

**Contributing?**

- Review [COPILOT_WORKFLOW.md](./COPILOT_WORKFLOW.md) for development guidelines
- Follow the PR checklist and code style guidelines
- Keep PRs small and focused
- Update documentation when behavior changes

## Documentation Maintenance

When updating documentation:

- **PROJECT_CONTEXT.md**: Update when setup instructions or project structure changes
- **REPO_MAP.md**: Update when new files/folders are added or paths change
- **COPILOT_WORKFLOW.md**: Update when development practices or guidelines change
- **Strategy READMEs**: Update in the strategy folder (e.g., `strategies/supply_demand_v1/README.md`) when strategy behavior changes

## Additional Resources

- [Trading Strategy SDK Documentation](https://tradingstrategy.ai/docs/)
- [Trading Strategy Community Discord](https://tradingstrategy.ai/community#discord)
- [Main Repository README](../README.md)
