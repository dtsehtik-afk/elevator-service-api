"""Daily schedule builder — Nearest Neighbor algorithm with priority ordering."""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.elevator import Elevator
from app.models.maintenance import MaintenanceSchedule
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.services.assignment_service import haversine_distance

# Estimated handling time in minutes per fault type
HANDLING_TIME: Dict[str, int] = {
    "MECHANICAL": 60,
    "ELECTRICAL": 75,
    "SOFTWARE": 45,
    "STUCK": 30,
    "DOOR": 40,
    "OTHER": 50,
    "QUARTERLY": 90,
    "SEMI_ANNUAL": 120,
    "ANNUAL": 180,
    "INSPECTION": 60,
}

TRAVEL_TIME_MINUTES = 20

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _nearest_neighbor_sort(
    stops: List[Dict[str, Any]],
    start_lat: float,
    start_lon: float,
) -> List[Dict[str, Any]]:
    """Sort a list of stops using the Nearest Neighbor heuristic.

    Starts from the technician's current position and greedily picks the
    closest unvisited stop next.

    Args:
        stops: List of stop dicts that each contain ``lat`` and ``lon`` keys.
        start_lat: Technician's starting latitude.
        start_lon: Technician's starting longitude.

    Returns:
        Sorted list of stops.
    """
    remaining = list(stops)
    ordered: List[Dict[str, Any]] = []
    current_lat, current_lon = start_lat, start_lon

    while remaining:
        closest = min(
            remaining,
            key=lambda s: haversine_distance(
                current_lat, current_lon, s["lat"], s["lon"]
            ),
        )
        ordered.append(closest)
        current_lat, current_lon = closest["lat"], closest["lon"]
        remaining.remove(closest)

    return ordered


def build_daily_schedule(
    db: Session, technician_id: uuid.UUID, target_date: date
) -> Optional[Dict[str, Any]]:
    """Build the optimised daily schedule for a technician on a given date.

    Algorithm:
    1. Collect all assigned service calls + scheduled maintenances for the day.
    2. Group by priority: CRITICAL → HIGH → MEDIUM → LOW.
    3. Within each group apply Nearest Neighbor sorting.
    4. Estimate arrival and duration times assuming 20 min travel between stops.
    5. Return structured schedule response.

    Args:
        db: Database session.
        technician_id: UUID of the technician.
        target_date: The date to build the schedule for.

    Returns:
        Schedule dict or None if technician is not found.
    """
    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        return None

    # --- Collect service calls assigned to this technician for target_date ---
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == technician_id,
            Assignment.assigned_at >= day_start,
            Assignment.assigned_at <= day_end,
        )
        .all()
    )
    call_ids = [a.service_call_id for a in assignments]
    service_calls = (
        db.query(ServiceCall)
        .filter(
            ServiceCall.id.in_(call_ids),
            ServiceCall.status.in_(["ASSIGNED", "IN_PROGRESS", "OPEN"]),
        )
        .all()
    ) if call_ids else []

    # --- Collect maintenance events for target_date ---
    maintenances = (
        db.query(MaintenanceSchedule)
        .filter(
            MaintenanceSchedule.technician_id == technician_id,
            MaintenanceSchedule.scheduled_date == target_date,
            MaintenanceSchedule.status == "SCHEDULED",
        )
        .all()
    )

    # --- Build raw stop list ---
    raw_stops: List[Dict[str, Any]] = []

    for call in service_calls:
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        lat = 32.0853  # Default: Tel Aviv
        lon = 34.7818
        raw_stops.append(
            {
                "type": "SERVICE_CALL",
                "id": str(call.id),
                "priority": call.priority,
                "priority_order": PRIORITY_ORDER.get(call.priority, 3),
                "fault_type": call.fault_type,
                "duration": HANDLING_TIME.get(call.fault_type, 50),
                "lat": lat,
                "lon": lon,
                "elevator": {
                    "id": str(elevator.id) if elevator else None,
                    "address": elevator.address if elevator else "Unknown",
                    "city": elevator.city if elevator else "Unknown",
                    "building_name": elevator.building_name if elevator else None,
                },
            }
        )

    for maint in maintenances:
        elevator = db.query(Elevator).filter(Elevator.id == maint.elevator_id).first()
        lat = 32.0853
        lon = 34.7818
        raw_stops.append(
            {
                "type": "MAINTENANCE",
                "id": str(maint.id),
                "priority": "MEDIUM",  # Maintenance treated as MEDIUM priority
                "priority_order": PRIORITY_ORDER.get("MEDIUM", 2),
                "fault_type": maint.maintenance_type,
                "duration": HANDLING_TIME.get(maint.maintenance_type, 90),
                "lat": lat,
                "lon": lon,
                "elevator": {
                    "id": str(elevator.id) if elevator else None,
                    "address": elevator.address if elevator else "Unknown",
                    "city": elevator.city if elevator else "Unknown",
                    "building_name": elevator.building_name if elevator else None,
                },
                "maintenance_type": maint.maintenance_type,
            }
        )

    if not raw_stops:
        return {
            "technician": {
                "id": str(tech.id),
                "name": tech.name,
                "email": tech.email,
            },
            "date": target_date.isoformat(),
            "total_stops": 0,
            "estimated_end_time": "08:00",
            "stops": [],
        }

    # --- Sort: priority first, then Nearest Neighbor within each group ---
    start_lat = tech.current_latitude or 32.0853
    start_lon = tech.current_longitude or 34.7818

    priority_groups: Dict[int, List[Dict[str, Any]]] = {}
    for stop in raw_stops:
        p = stop["priority_order"]
        priority_groups.setdefault(p, []).append(stop)

    ordered_stops: List[Dict[str, Any]] = []
    current_lat, current_lon = start_lat, start_lon

    for priority_level in sorted(priority_groups.keys()):
        group = priority_groups[priority_level]
        sorted_group = _nearest_neighbor_sort(group, current_lat, current_lon)
        ordered_stops.extend(sorted_group)
        if sorted_group:
            last = sorted_group[-1]
            current_lat, current_lon = last["lat"], last["lon"]

    # --- Calculate estimated arrival times (workday starts at 08:00) ---
    current_time = datetime.combine(target_date, datetime.min.time().replace(hour=8))

    result_stops: List[Dict[str, Any]] = []
    for order, stop in enumerate(ordered_stops, start=1):
        arrival = current_time + timedelta(minutes=TRAVEL_TIME_MINUTES if order > 1 else 0)
        stop_result: Dict[str, Any] = {
            "order": order,
            "type": stop["type"],
            "elevator": stop["elevator"],
            "priority": stop["priority"],
            "fault_type": stop["fault_type"],
            "estimated_arrival": arrival.strftime("%H:%M"),
            "estimated_duration_minutes": stop["duration"],
        }
        if stop["type"] == "SERVICE_CALL":
            stop_result["service_call_id"] = stop["id"]
        else:
            stop_result["maintenance_id"] = stop["id"]
            stop_result["maintenance_type"] = stop.get("maintenance_type")

        result_stops.append(stop_result)
        current_time = arrival + timedelta(minutes=stop["duration"])

    estimated_end = current_time.strftime("%H:%M")

    return {
        "technician": {
            "id": str(tech.id),
            "name": tech.name,
            "email": tech.email,
        },
        "date": target_date.isoformat(),
        "total_stops": len(result_stops),
        "estimated_end_time": estimated_end,
        "stops": result_stops,
    }
