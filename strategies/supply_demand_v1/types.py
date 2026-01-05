"""Canonical Type Definitions for Supply & Demand V1 Strategy

This module contains the single source of truth for all enums and shared types
used across the Supply & Demand V1 strategy.

All modules in the supply_demand_v1 package should import enums from this module
to avoid duplicate definitions and ensure type consistency.

Purpose:
    - Eliminate duplicate enum definitions across strategy_core.py and strategy.py
    - Provide a single canonical location for all shared types
    - Ensure enum identity checks work correctly across modules
    - Make comparisons robust and avoid subtle bugs
"""

from enum import Enum


class CurveLocation(Enum):
    """Price location within the HTF range"""
    HIGH = "high"
    EQUILIBRIUM = "equilibrium"
    LOW = "low"


class TrendDirection(Enum):
    """Trend direction on ITF"""
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


class ZoneType(Enum):
    """Type of supply/demand zone"""
    DEMAND = "demand"  # Drop-Base-Rally (DBR)
    SUPPLY = "supply"  # Rally-Base-Drop (RBD)


class EntryMode(Enum):
    """Entry execution mode"""
    LIMIT = "limit"  # Place limit order at proximal
    CONFIRMATION = "confirmation"  # Wait for price to reverse through proximal


class OrderState(Enum):
    """Order state for limit orders"""
    PENDING = "pending"  # Order placed but not filled
    FILLED = "filled"  # Order filled
    CANCELLED = "cancelled"  # Order cancelled (TTL expired)


class ViolationType(Enum):
    """Types of integrity violations"""
    LOOK_AHEAD = "look_ahead"
    ENTRY_BEFORE_ZONE = "entry_before_zone"
    R_CALCULATION_MISMATCH = "r_calculation_mismatch"
    INSUFFICIENT_R = "insufficient_r"


__all__ = [
    "CurveLocation",
    "TrendDirection",
    "ZoneType",
    "EntryMode",
    "OrderState",
    "ViolationType",
]
