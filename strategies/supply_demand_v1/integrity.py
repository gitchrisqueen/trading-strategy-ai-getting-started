"""Backtest Integrity Report for Supply & Demand V1 Strategy

This module provides validation functions to ensure backtest integrity by checking:
1. No look-ahead bias - zones cannot be used before their creation
2. Entry timing - entries must occur after zone creation
3. R calculation consistency - verify R = abs(target-entry)/abs(entry-stop)
4. Minimum R enforcement - flag trades with planned R < 3.0
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Import canonical enum from types module
from .types import ViolationType


@dataclass
class IntegrityViolation:
    """Represents a single integrity violation
    
    Attributes:
        violation_type: Type of violation
        trade: The trade that violated integrity
        reason: Human-readable explanation
        details: Additional details for debugging
    """
    violation_type: ViolationType
    trade: Dict[str, Any]
    reason: str
    details: Dict[str, Any]


@dataclass
class IntegrityReport:
    """Complete integrity report for a backtest
    
    Attributes:
        total_trades: Total number of trades analyzed
        violations: List of all violations found
        violation_counts: Count of violations by type
        clean: Whether the backtest passed all integrity checks
    """
    total_trades: int
    violations: List[IntegrityViolation]
    violation_counts: Dict[ViolationType, int]
    clean: bool


def validate_no_lookahead(
    trade: Dict[str, Any],
    zone_created_at_idx: int,
    zone_created_time: Optional[Any],
    decision_idx: int,
    decision_time: Optional[Any]
) -> Optional[IntegrityViolation]:
    """Validate that a zone was not used before its creation (no look-ahead bias)
    
    A zone cannot be used for trading decisions until after the leg-out is complete
    and the zone has been created. This checks that the decision to trade was made
    after the zone's creation timestamp.
    
    Args:
        trade: Trade dictionary with entry details
        zone_created_at_idx: Index where the zone was created (legout_end_idx)
        zone_created_time: Timestamp when zone was created
        decision_idx: Index where the trading decision was made
        decision_time: Timestamp of the trading decision
    
    Returns:
        IntegrityViolation if look-ahead detected, None otherwise
    """
    # Check index-based ordering
    if decision_idx <= zone_created_at_idx:
        return IntegrityViolation(
            violation_type=ViolationType.LOOK_AHEAD,
            trade=trade,
            reason=f"Trading decision made at index {decision_idx} before or at zone creation index {zone_created_at_idx}",
            details={
                'zone_created_at_idx': zone_created_at_idx,
                'decision_idx': decision_idx,
                'zone_created_time': str(zone_created_time) if zone_created_time else None,
                'decision_time': str(decision_time) if decision_time else None,
            }
        )
    
    # Check timestamp-based ordering if available
    if zone_created_time is not None and decision_time is not None:
        if decision_time <= zone_created_time:
            return IntegrityViolation(
                violation_type=ViolationType.LOOK_AHEAD,
                trade=trade,
                reason=f"Trading decision made at {decision_time} before or at zone creation time {zone_created_time}",
                details={
                    'zone_created_at_idx': zone_created_at_idx,
                    'decision_idx': decision_idx,
                    'zone_created_time': str(zone_created_time),
                    'decision_time': str(decision_time),
                }
            )
    
    return None


def validate_entry_after_zone_creation(
    trade: Dict[str, Any],
    zone_created_at_idx: int,
    zone_created_time: Optional[Any],
    entry_idx: int,
    entry_time: Optional[Any]
) -> Optional[IntegrityViolation]:
    """Validate that entry occurred after zone creation
    
    The actual trade entry must happen after the zone was created. This is similar
    to look-ahead validation but specifically checks the entry execution timing.
    
    Args:
        trade: Trade dictionary with entry details
        zone_created_at_idx: Index where the zone was created
        zone_created_time: Timestamp when zone was created
        entry_idx: Index where entry occurred
        entry_time: Timestamp of entry
    
    Returns:
        IntegrityViolation if entry before creation, None otherwise
    """
    # Check index-based ordering
    if entry_idx <= zone_created_at_idx:
        return IntegrityViolation(
            violation_type=ViolationType.ENTRY_BEFORE_ZONE,
            trade=trade,
            reason=f"Entry at index {entry_idx} before or at zone creation index {zone_created_at_idx}",
            details={
                'zone_created_at_idx': zone_created_at_idx,
                'entry_idx': entry_idx,
                'zone_created_time': str(zone_created_time) if zone_created_time else None,
                'entry_time': str(entry_time) if entry_time else None,
            }
        )
    
    # Check timestamp-based ordering if available
    if zone_created_time is not None and entry_time is not None:
        if entry_time <= zone_created_time:
            return IntegrityViolation(
                violation_type=ViolationType.ENTRY_BEFORE_ZONE,
                trade=trade,
                reason=f"Entry at {entry_time} before or at zone creation time {zone_created_time}",
                details={
                    'zone_created_at_idx': zone_created_at_idx,
                    'entry_idx': entry_idx,
                    'zone_created_time': str(zone_created_time),
                    'entry_time': str(entry_time),
                }
            )
    
    return None


def validate_planned_r_calculation(
    trade: Dict[str, Any],
    tolerance: float = 0.01
) -> Optional[IntegrityViolation]:
    """Validate that R multiple calculation is consistent
    
    Verifies that the planned R multiple was calculated correctly at decision time:
    R = abs(target - entry) / abs(entry - stop)
    
    Args:
        trade: Trade dictionary containing entry_price, stop_loss, take_profit, and r_multiple
        tolerance: Acceptable relative tolerance for floating point comparison (default 1%)
    
    Returns:
        IntegrityViolation if calculation mismatch detected, None otherwise
    """
    entry = trade.get('entry_price')
    stop = trade.get('stop_loss')
    target = trade.get('take_profit')
    recorded_r = trade.get('r_multiple')
    
    # Check if all required fields are present
    if entry is None or stop is None or target is None or recorded_r is None:
        return IntegrityViolation(
            violation_type=ViolationType.R_CALCULATION_MISMATCH,
            trade=trade,
            reason="Missing required fields for R calculation",
            details={
                'has_entry': entry is not None,
                'has_stop': stop is not None,
                'has_target': target is not None,
                'has_r_multiple': recorded_r is not None,
            }
        )
    
    # Calculate expected R
    risk = abs(entry - stop)
    
    if risk == 0:
        return IntegrityViolation(
            violation_type=ViolationType.R_CALCULATION_MISMATCH,
            trade=trade,
            reason="Invalid trade plan: risk is zero (entry equals stop)",
            details={
                'entry_price': entry,
                'stop_loss': stop,
                'risk': risk,
            }
        )
    
    reward = abs(target - entry)
    expected_r = reward / risk
    
    # Check if recorded R matches expected R within tolerance
    relative_error = abs(recorded_r - expected_r) / max(abs(expected_r), 1e-10)
    
    if relative_error > tolerance:
        return IntegrityViolation(
            violation_type=ViolationType.R_CALCULATION_MISMATCH,
            trade=trade,
            reason=f"R calculation mismatch: recorded {recorded_r:.4f} vs expected {expected_r:.4f} (error: {relative_error:.2%})",
            details={
                'entry_price': entry,
                'stop_loss': stop,
                'take_profit': target,
                'risk': risk,
                'reward': reward,
                'recorded_r': recorded_r,
                'expected_r': expected_r,
                'relative_error': relative_error,
                'tolerance': tolerance,
            }
        )
    
    return None


def validate_minimum_r(
    trade: Dict[str, Any],
    min_r: float = 3.0
) -> Optional[IntegrityViolation]:
    """Validate that planned R meets minimum requirement
    
    Flags trades where the planned R multiple at decision time was below
    the minimum threshold (default 3.0).
    
    Args:
        trade: Trade dictionary containing r_multiple (planned R at decision time)
        min_r: Minimum acceptable R multiple (default 3.0)
    
    Returns:
        IntegrityViolation if R is below minimum, None otherwise
    """
    # Get the planned R (not the actual outcome R)
    # The trade dict should contain 'planned_r' for the decision-time R
    # Fallback to 'r_multiple' if 'planned_r' not present
    planned_r = trade.get('planned_r')
    if planned_r is None:
        planned_r = trade.get('r_multiple')
    
    if planned_r is None:
        return IntegrityViolation(
            violation_type=ViolationType.INSUFFICIENT_R,
            trade=trade,
            reason="Missing planned R multiple for validation",
            details={'min_r': min_r}
        )
    
    if planned_r < min_r:
        return IntegrityViolation(
            violation_type=ViolationType.INSUFFICIENT_R,
            trade=trade,
            reason=f"Planned R of {planned_r:.4f} is below minimum requirement of {min_r:.4f}",
            details={
                'planned_r': planned_r,
                'min_r': min_r,
                'shortfall': min_r - planned_r,
            }
        )
    
    return None


def run_integrity_checks(
    trades: List[Dict[str, Any]],
    min_r: float = 3.0,
    r_tolerance: float = 0.01
) -> IntegrityReport:
    """Run all integrity checks on a list of trades
    
    This is the main entry point for running integrity validation on backtest results.
    It runs all validation functions and aggregates the results into a report.
    
    Args:
        trades: List of trade dictionaries. Each trade should contain:
            - entry_price: Entry price
            - stop_loss: Stop loss price
            - take_profit: Take profit target
            - r_multiple: Recorded R multiple (or planned_r if different)
            - zone_created_at_idx: Index where zone was created (optional)
            - zone_created_time: Timestamp when zone was created (optional)
            - decision_idx: Index where decision was made (optional)
            - decision_time: Timestamp of decision (optional)
            - entry_idx: Index where entry occurred (optional)
            - entry_time: Timestamp of entry (optional)
        min_r: Minimum acceptable R multiple
        r_tolerance: Tolerance for R calculation validation
    
    Returns:
        IntegrityReport with all violations found
    """
    violations = []
    
    for trade in trades:
        # Validate no look-ahead bias (if data available)
        zone_created_at_idx = trade.get('zone_created_at_idx')
        zone_created_time = trade.get('zone_created_time')
        decision_idx = trade.get('decision_idx')
        decision_time = trade.get('decision_time')
        
        if zone_created_at_idx is not None and decision_idx is not None:
            violation = validate_no_lookahead(
                trade, zone_created_at_idx, zone_created_time,
                decision_idx, decision_time
            )
            if violation:
                violations.append(violation)
        
        # Validate entry after zone creation (if data available)
        entry_idx = trade.get('entry_idx')
        entry_time = trade.get('entry_time')
        
        if zone_created_at_idx is not None and entry_idx is not None:
            violation = validate_entry_after_zone_creation(
                trade, zone_created_at_idx, zone_created_time,
                entry_idx, entry_time
            )
            if violation:
                violations.append(violation)
        
        # Validate R calculation
        violation = validate_planned_r_calculation(trade, r_tolerance)
        if violation:
            violations.append(violation)
        
        # Validate minimum R
        violation = validate_minimum_r(trade, min_r)
        if violation:
            violations.append(violation)
    
    # Count violations by type
    violation_counts = {vtype: 0 for vtype in ViolationType}
    for violation in violations:
        violation_counts[violation.violation_type] += 1
    
    report = IntegrityReport(
        total_trades=len(trades),
        violations=violations,
        violation_counts=violation_counts,
        clean=len(violations) == 0
    )
    
    return report


def print_integrity_report(report: IntegrityReport, verbose: bool = True):
    """Print integrity report in a human-readable format
    
    Args:
        report: IntegrityReport to print
        verbose: If True, print details of each violation
    """
    print("\n" + "=" * 80)
    print("BACKTEST INTEGRITY REPORT")
    print("=" * 80)
    
    print(f"\nTotal trades analyzed: {report.total_trades}")
    print(f"Status: {'✓ CLEAN' if report.clean else '✗ VIOLATIONS FOUND'}")
    
    print("\n" + "-" * 80)
    print("Violation Summary:")
    print("-" * 80)
    
    for vtype, count in report.violation_counts.items():
        status = "✓" if count == 0 else "✗"
        print(f"{status} {vtype.value.replace('_', ' ').title()}: {count}")
    
    if verbose and not report.clean:
        print("\n" + "-" * 80)
        print("Violation Details:")
        print("-" * 80)
        
        for i, violation in enumerate(report.violations, 1):
            print(f"\n[{i}] {violation.violation_type.value.upper()}")
            print(f"    Reason: {violation.reason}")
            
            # Print key trade info
            trade = violation.trade
            if 'symbol' in trade:
                print(f"    Symbol: {trade['symbol']}")
            if 'entry_time' in trade:
                print(f"    Entry Time: {trade['entry_time']}")
            if 'entry_price' in trade:
                print(f"    Entry: ${trade['entry_price']:.2f}")
            if 'zone_type' in trade:
                print(f"    Zone Type: {trade['zone_type']}")
            
            # Print violation-specific details
            if violation.details:
                print(f"    Details:")
                for key, value in violation.details.items():
                    if value is not None:
                        print(f"      - {key}: {value}")
    
    print("\n" + "=" * 80)
