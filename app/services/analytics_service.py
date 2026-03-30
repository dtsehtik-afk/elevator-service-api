"""Analytics queries — aggregated statistics for management reporting."""

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.elevator import Elevator
from app.models.service_call import ServiceCall
from app.models.technician import Technician


def get_recurring_fault_elevators(db: Session) -> List[Dict[str, Any]]:
    """Return elevators with 3 or more service calls in the last 90 days.

    Args:
        db: Database session.

    Returns:
        List of dicts: elevator info + call count.
    """
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

    # Fetch all recent calls and aggregate in Python to stay DB-agnostic
    recent_calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.created_at >= ninety_days_ago)
        .all()
    )

    # Aggregate per elevator
    elevator_stats: Dict[Any, Dict[str, int]] = {}
    for call in recent_calls:
        eid = call.elevator_id
        if eid not in elevator_stats:
            elevator_stats[eid] = {"total": 0, "recurring": 0}
        elevator_stats[eid]["total"] += 1
        if call.is_recurring:
            elevator_stats[eid]["recurring"] += 1

    # Filter to >= 3 calls
    eligible_ids = [eid for eid, stats in elevator_stats.items() if stats["total"] >= 3]
    if not eligible_ids:
        return []

    elevators = (
        db.query(Elevator)
        .filter(Elevator.id.in_(eligible_ids))
        .all()
    )

    results = [
        {
            "elevator_id": str(e.id),
            "address": e.address,
            "city": e.city,
            "building_name": e.building_name,
            "risk_score": e.risk_score,
            "call_count_90_days": elevator_stats[e.id]["total"],
            "recurring_count": elevator_stats[e.id]["recurring"],
        }
        for e in elevators
    ]
    return sorted(results, key=lambda x: x["call_count_90_days"], reverse=True)


def get_technician_performance(db: Session) -> List[Dict[str, Any]]:
    """Compute average resolution time and assignment counts per technician.

    Args:
        db: Database session.

    Returns:
        List of dicts with performance metrics per technician.
    """
    technicians = db.query(Technician).filter(Technician.is_active == True).all()  # noqa: E712
    results: List[Dict[str, Any]] = []

    for tech in technicians:
        assignments = (
            db.query(Assignment)
            .filter(Assignment.technician_id == tech.id)
            .all()
        )
        call_ids = [a.service_call_id for a in assignments]

        if not call_ids:
            results.append(
                {
                    "technician_id": str(tech.id),
                    "name": tech.name,
                    "email": tech.email,
                    "total_assigned": 0,
                    "total_resolved": 0,
                    "avg_resolution_hours": None,
                }
            )
            continue

        calls = db.query(ServiceCall).filter(ServiceCall.id.in_(call_ids)).all()
        resolved = [c for c in calls if c.resolved_at and c.created_at]
        total_hours = sum(
            (c.resolved_at - c.created_at).total_seconds() / 3600 for c in resolved
        )
        avg = round(total_hours / len(resolved), 2) if resolved else None

        results.append(
            {
                "technician_id": str(tech.id),
                "name": tech.name,
                "email": tech.email,
                "total_assigned": len(assignments),
                "total_resolved": len(resolved),
                "avg_resolution_hours": avg,
            }
        )

    return sorted(results, key=lambda x: x["total_assigned"], reverse=True)


def get_monthly_summary(db: Session, year: int, month: int) -> Dict[str, Any]:
    """Return aggregated service call statistics for a specific month.

    Args:
        db: Database session.
        year: The year (e.g. 2024).
        month: The month number (1-12).

    Returns:
        Summary dict with totals, averages, and breakdowns.
    """
    first_day = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num, 23, 59, 59, tzinfo=timezone.utc)

    calls = (
        db.query(ServiceCall)
        .filter(
            ServiceCall.created_at >= first_day,
            ServiceCall.created_at <= last_day,
        )
        .all()
    )

    total = len(calls)
    resolved = [c for c in calls if c.status in ("RESOLVED", "CLOSED")]
    recurring = [c for c in calls if c.is_recurring]

    by_priority: Dict[str, int] = {}
    by_fault: Dict[str, int] = {}
    for c in calls:
        by_priority[c.priority] = by_priority.get(c.priority, 0) + 1
        by_fault[c.fault_type] = by_fault.get(c.fault_type, 0) + 1

    total_hours = sum(
        (c.resolved_at - c.created_at).total_seconds() / 3600
        for c in resolved
        if c.resolved_at and c.created_at
    )
    avg_hours = round(total_hours / len(resolved), 2) if resolved else None

    return {
        "year": year,
        "month": month,
        "total_calls": total,
        "resolved_calls": len(resolved),
        "recurring_calls": len(recurring),
        "resolution_rate": round(len(resolved) / total * 100, 1) if total else 0,
        "avg_resolution_hours": avg_hours,
        "calls_by_priority": by_priority,
        "calls_by_fault_type": by_fault,
    }


def get_risk_elevators(db: Session, threshold: float = 70.0) -> List[Dict[str, Any]]:
    """Return elevators with risk_score above the given threshold.

    Args:
        db: Database session.
        threshold: Minimum risk score (default 70).

    Returns:
        List of elevator dicts sorted by risk_score descending.
    """
    elevators = (
        db.query(Elevator)
        .filter(Elevator.risk_score > threshold, Elevator.status == "ACTIVE")
        .order_by(Elevator.risk_score.desc())
        .all()
    )

    return [
        {
            "elevator_id": str(e.id),
            "address": e.address,
            "city": e.city,
            "building_name": e.building_name,
            "status": e.status,
            "risk_score": e.risk_score,
            "last_service_date": e.last_service_date.isoformat() if e.last_service_date else None,
            "next_service_date": e.next_service_date.isoformat() if e.next_service_date else None,
        }
        for e in elevators
    ]
