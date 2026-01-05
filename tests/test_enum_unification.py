"""Test enum identity and unification across supply_demand_v1 modules

This test suite validates that:
1. All enum imports reference the same canonical class from types.py
2. Enum identity checks work correctly (is comparison)
3. Enum equality checks work correctly (== comparison)
4. No duplicate enum definitions exist
"""

import pytest


def test_enum_identity_from_types():
    """Test that enums imported from types.py are the canonical definitions"""
    from strategies.supply_demand_v1.types import (
        OrderState,
        ZoneType,
        CurveLocation,
        TrendDirection,
        EntryMode,
        ViolationType,
    )
    
    # Test that enum values exist
    assert OrderState.PENDING
    assert OrderState.FILLED
    assert OrderState.CANCELLED
    
    assert ZoneType.DEMAND
    assert ZoneType.SUPPLY
    
    assert CurveLocation.HIGH
    assert CurveLocation.EQUILIBRIUM
    assert CurveLocation.LOW
    
    assert TrendDirection.UP
    assert TrendDirection.DOWN
    assert TrendDirection.SIDEWAYS
    
    assert EntryMode.LIMIT
    assert EntryMode.CONFIRMATION
    
    assert ViolationType.LOOK_AHEAD
    assert ViolationType.ENTRY_BEFORE_ZONE
    assert ViolationType.R_CALCULATION_MISMATCH
    assert ViolationType.INSUFFICIENT_R


def test_enum_identity_from_strategy_core():
    """Test that enums imported from strategy_core reference types.py"""
    from strategies.supply_demand_v1.strategy_core import (
        OrderState as CoreOrderState,
        ZoneType as CoreZoneType,
        CurveLocation as CoreCurveLocation,
        TrendDirection as CoreTrendDirection,
        EntryMode as CoreEntryMode,
    )
    from strategies.supply_demand_v1.types import (
        OrderState,
        ZoneType,
        CurveLocation,
        TrendDirection,
        EntryMode,
    )
    
    # Test identity - these should be the SAME class object
    assert CoreOrderState is OrderState, "OrderState should be the same class from types.py"
    assert CoreZoneType is ZoneType, "ZoneType should be the same class from types.py"
    assert CoreCurveLocation is CurveLocation, "CurveLocation should be the same class from types.py"
    assert CoreTrendDirection is TrendDirection, "TrendDirection should be the same class from types.py"
    assert CoreEntryMode is EntryMode, "EntryMode should be the same class from types.py"


def test_enum_identity_from_strategy():
    """Test that enums imported from strategy reference types.py"""
    from strategies.supply_demand_v1.strategy import (
        OrderState as StratOrderState,
        ZoneType as StratZoneType,
        CurveLocation as StratCurveLocation,
        TrendDirection as StratTrendDirection,
        EntryMode as StratEntryMode,
    )
    from strategies.supply_demand_v1.types import (
        OrderState,
        ZoneType,
        CurveLocation,
        TrendDirection,
        EntryMode,
    )
    
    # Test identity - these should be the SAME class object
    assert StratOrderState is OrderState, "OrderState should be the same class from types.py"
    assert StratZoneType is ZoneType, "ZoneType should be the same class from types.py"
    assert StratCurveLocation is CurveLocation, "CurveLocation should be the same class from types.py"
    assert StratTrendDirection is TrendDirection, "TrendDirection should be the same class from types.py"
    assert StratEntryMode is EntryMode, "EntryMode should be the same class from types.py"


def test_enum_identity_from_init():
    """Test that enums imported from __init__ reference types.py"""
    from strategies.supply_demand_v1 import (
        OrderState as InitOrderState,
        ZoneType as InitZoneType,
        CurveLocation as InitCurveLocation,
        TrendDirection as InitTrendDirection,
        EntryMode as InitEntryMode,
        ViolationType as InitViolationType,
    )
    from strategies.supply_demand_v1.types import (
        OrderState,
        ZoneType,
        CurveLocation,
        TrendDirection,
        EntryMode,
        ViolationType,
    )
    
    # Test identity - these should be the SAME class object
    assert InitOrderState is OrderState, "OrderState should be the same class from types.py"
    assert InitZoneType is ZoneType, "ZoneType should be the same class from types.py"
    assert InitCurveLocation is CurveLocation, "CurveLocation should be the same class from types.py"
    assert InitTrendDirection is TrendDirection, "TrendDirection should be the same class from types.py"
    assert InitEntryMode is EntryMode, "EntryMode should be the same class from types.py"
    assert InitViolationType is ViolationType, "ViolationType should be the same class from types.py"


def test_enum_identity_from_integrity():
    """Test that ViolationType imported from integrity references types.py"""
    from strategies.supply_demand_v1.integrity import ViolationType as IntegrityViolationType
    from strategies.supply_demand_v1.types import ViolationType
    
    # Test identity - these should be the SAME class object
    assert IntegrityViolationType is ViolationType, "ViolationType should be the same class from types.py"


def test_enum_comparison_works_correctly():
    """Test that enum comparisons work correctly across imports"""
    from strategies.supply_demand_v1.strategy import OrderState as StratOrderState
    from strategies.supply_demand_v1.strategy_core import OrderState as CoreOrderState
    from strategies.supply_demand_v1.types import OrderState
    
    # Create enum values from different imports
    strat_filled = StratOrderState.FILLED
    core_filled = CoreOrderState.FILLED
    types_filled = OrderState.FILLED
    
    # Test identity comparison (should work since they're the same class)
    assert strat_filled is core_filled
    assert strat_filled is types_filled
    assert core_filled is types_filled
    
    # Test equality comparison (should definitely work)
    assert strat_filled == core_filled
    assert strat_filled == types_filled
    assert core_filled == types_filled


def test_zone_type_comparison():
    """Test ZoneType comparisons work correctly"""
    from strategies.supply_demand_v1.strategy import ZoneType as StratZoneType
    from strategies.supply_demand_v1.strategy_core import ZoneType as CoreZoneType
    from strategies.supply_demand_v1.types import ZoneType
    
    # Create enum values
    strat_demand = StratZoneType.DEMAND
    core_demand = CoreZoneType.DEMAND
    types_demand = ZoneType.DEMAND
    
    # Test comparisons
    assert strat_demand is core_demand
    assert strat_demand is types_demand
    assert strat_demand == core_demand
    assert strat_demand == types_demand


def test_no_duplicate_enum_classes():
    """Test that we don't have duplicate enum class definitions"""
    import strategies.supply_demand_v1.types as types_module
    import strategies.supply_demand_v1.strategy as strategy_module
    import strategies.supply_demand_v1.strategy_core as core_module
    
    # Get the enum classes
    types_order_state = types_module.OrderState
    strat_order_state = strategy_module.OrderState
    core_order_state = core_module.OrderState
    
    # Verify they are the exact same class object (not just equal, but identical)
    assert id(types_order_state) == id(strat_order_state), \
        "strategy.OrderState should be the exact same object as types.OrderState"
    assert id(types_order_state) == id(core_order_state), \
        "strategy_core.OrderState should be the exact same object as types.OrderState"
    assert id(strat_order_state) == id(core_order_state), \
        "strategy.OrderState and strategy_core.OrderState should be the exact same object"


def test_enum_values_consistency():
    """Test that enum values are consistent across all imports"""
    from strategies.supply_demand_v1.types import OrderState, ZoneType, CurveLocation, TrendDirection, EntryMode
    
    # OrderState
    assert OrderState.PENDING.value == "pending"
    assert OrderState.FILLED.value == "filled"
    assert OrderState.CANCELLED.value == "cancelled"
    
    # ZoneType
    assert ZoneType.DEMAND.value == "demand"
    assert ZoneType.SUPPLY.value == "supply"
    
    # CurveLocation
    assert CurveLocation.HIGH.value == "high"
    assert CurveLocation.EQUILIBRIUM.value == "equilibrium"
    assert CurveLocation.LOW.value == "low"
    
    # TrendDirection
    assert TrendDirection.UP.value == "up"
    assert TrendDirection.DOWN.value == "down"
    assert TrendDirection.SIDEWAYS.value == "sideways"
    
    # EntryMode
    assert EntryMode.LIMIT.value == "limit"
    assert EntryMode.CONFIRMATION.value == "confirmation"


def test_backward_compatibility_imports():
    """Test that existing import patterns still work"""
    # Old pattern: import from strategy.py
    from strategies.supply_demand_v1.strategy import (
        OrderState,
        ZoneType,
        CurveLocation,
        TrendDirection,
        EntryMode,
    )
    
    # These should work without errors
    assert OrderState.PENDING
    assert ZoneType.DEMAND
    assert CurveLocation.HIGH
    assert TrendDirection.UP
    assert EntryMode.LIMIT
    
    # Old pattern: import from __init__.py
    from strategies.supply_demand_v1 import (
        OrderState as InitOrderState,
        ZoneType as InitZoneType,
    )
    
    assert InitOrderState.PENDING
    assert InitZoneType.DEMAND
