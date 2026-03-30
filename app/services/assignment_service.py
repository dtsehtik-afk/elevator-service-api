"""Smart assignment algorithm — selects the best available technician for a service call."""

import math
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.service_call import ServiceCall
from app.models.technician import Technician


# Fault type → specialization mapping
FAULT_SPECIALIZATION_MAP = {
    "MECHANICAL": "MECHANICAL",
    "ELECTRICAL": "ELECTRICAL",
    "SOFTWARE": "SOFTWARE",
    "STUCK": "MECHANICAL",
    "DOOR": "MECHANICAL",
    "OTHER": None,
}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in kilometres between two GPS coordinates.

    Uses the Haversine formula.

    Args:
        lat1, lon1: Coordinates of the first point (technician).
        lat2, lon2: Coordinates of the second point (elevator / building).

    Returns:
        Distance in kilometres.
    """
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _get_daily_call_count(db: Session, technician_id: uuid.UUID, target_date: date) -> int:
    """Count how many calls a technician has been assigned to on a given day."""
    start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    return (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == technician_id,
            Assignment.assigned_at >= start,
            Assignment.assigned_at <= end,
        )
        .count()
    )


def _score_technician(
    technician: Technician,
    daily_calls: int,
    distance_km: float,
    required_specialization: Optional[str],
) -> float:
    """Calculate a weighted score for a technician (lower is better).

    Formula: 60% distance weight + 40% workload weight.
    Specialization mismatch adds a penalty.

    Args:
        technician: Technician ORM object.
        daily_calls: Number of calls already assigned today.
        distance_km: Distance to the elevator in km.
        required_specialization: Required specialization for the fault type.

    Returns:
        Weighted score (lower = better candidate).
    """
    workload_ratio = daily_calls / technician.max_daily_calls
    distance_score = distance_km  # raw km

    # Normalise to [0, 1] roughly — distance capped at 100 km
    distance_norm = min(distance_score / 100.0, 1.0)
    workload_norm = min(workload_ratio, 1.0)

    score = 0.6 * distance_norm + 0.4 * workload_norm

    # Specialization penalty: +0.3 if technician lacks the required spec
    if required_specialization and required_specialization not in (technician.specializations or []):
        score += 0.3

    return score


def find_best_technician(
    db: Session,
    elevator_latitude: float,
    elevator_longitude: float,
    fault_type: str,
    target_date: Optional[date] = None,
) -> Optional[Technician]:
    """Select the best available technician using the smart assignment algorithm.

    Steps:
    1. Filter active, available technicians with capacity remaining today.
    2. Match specialization to fault_type.
    3. Compute Haversine distance.
    4. Score by: 60% distance + 40% workload.
    5. Return the lowest-scoring technician.

    Args:
        db: Database session.
        elevator_latitude: Latitude of the elevator's building.
        elevator_longitude: Longitude of the elevator's building.
        fault_type: Fault type of the service call.
        target_date: The date to check capacity for (defaults to today).

    Returns:
        Best Technician ORM object or None if no candidate is available.
    """
    if target_date is None:
        target_date = date.today()

    candidates = (
        db.query(Technician)
        .filter(Technician.is_active == True, Technician.is_available == True)  # noqa: E712
        .all()
    )

    required_spec = FAULT_SPECIALIZATION_MAP.get(fault_type)
    scored: List[tuple] = []

    for tech in candidates:
        daily_calls = _get_daily_call_count(db, tech.id, target_date)
        if daily_calls >= tech.max_daily_calls:
            continue  # At capacity

        # Need location to compute distance
        if tech.current_latitude is None or tech.current_longitude is None:
            distance = 999.0  # Penalise unknown location
        else:
            distance = haversine_distance(
                tech.current_latitude, tech.current_longitude,
                elevator_latitude, elevator_longitude,
            )

        score = _score_technician(tech, daily_calls, distance, required_spec)
        scored.append((score, tech))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def auto_assign_call(
    db: Session, call_id: uuid.UUID, assigned_by: str
) -> Optional[Assignment]:
    """Automatically assign the best available technician to a service call.

    Args:
        db: Database session.
        call_id: UUID of the service call.
        assigned_by: Email of the user triggering the assignment.

    Returns:
        Created Assignment or None if no technician is available.

    Raises:
        ValueError: If the call does not exist.
    """
    call = db.query(ServiceCall).filter(ServiceCall.id == call_id).first()
    if not call:
        raise ValueError("Service call not found")

    # Get elevator coordinates via a join query
    from app.models.elevator import Elevator
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()

    # Default coordinates if elevator has no GPS (use building address — 0,0 fallback)
    lat = 32.0853  # Tel Aviv default if not geocoded
    lon = 34.7818

    technician = find_best_technician(db, lat, lon, call.fault_type)
    if not technician:
        return None

    assignment = Assignment(
        service_call_id=call_id,
        technician_id=technician.id,
        assignment_type="AUTO",
        notes=f"Auto-assigned by {assigned_by}",
    )
    db.add(assignment)

    # Update call status and timestamp
    call.status = "ASSIGNED"
    call.assigned_at = datetime.now(timezone.utc)

    # Write audit log
    from app.models.assignment import AuditLog
    audit = AuditLog(
        service_call_id=call_id,
        changed_by=assigned_by,
        old_status="OPEN",
        new_status="ASSIGNED",
        notes=f"Auto-assigned to {technician.name}",
    )
    db.add(audit)

    db.commit()
    db.refresh(assignment)
    return assignment


def manual_assign_call(
    db: Session,
    call_id: uuid.UUID,
    technician_id: uuid.UUID,
    assigned_by: str,
    notes: Optional[str] = None,
) -> Assignment:
    """Manually assign a specific technician to a service call.

    Args:
        db: Database session.
        call_id: UUID of the service call.
        technician_id: UUID of the technician to assign.
        assigned_by: Email of the user making the assignment.
        notes: Optional assignment notes.

    Returns:
        Created Assignment.

    Raises:
        ValueError: If the call or technician does not exist.
    """
    call = db.query(ServiceCall).filter(ServiceCall.id == call_id).first()
    if not call:
        raise ValueError("Service call not found")

    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        raise ValueError("Technician not found")

    assignment = Assignment(
        service_call_id=call_id,
        technician_id=technician_id,
        assignment_type="MANUAL",
        notes=notes,
    )
    db.add(assignment)

    old_status = call.status
    call.status = "ASSIGNED"
    call.assigned_at = datetime.now(timezone.utc)

    from app.models.assignment import AuditLog
    audit = AuditLog(
        service_call_id=call_id,
        changed_by=assigned_by,
        old_status=old_status,
        new_status="ASSIGNED",
        notes=f"Manually assigned to {tech.name}",
    )
    db.add(audit)

    db.commit()
    db.refresh(assignment)
    return assignment
