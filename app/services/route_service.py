"""
Route optimization service — builds an ordered daily route for technicians.

Algorithm: Nearest-Neighbor greedy TSP
  Start from technician's current GPS position.
  At each step, pick the closest unvisited open call.
  Repeat until all calls are ordered.

Triggered:
  1. When a technician shares their live location in the morning.
  2. When a new call is assigned to a technician already on a route.
"""

import logging
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.elevator import Elevator
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.services.maps_service import ensure_elevator_coords

logger = logging.getLogger(__name__)

# How far (km straight-line) to look for open calls to include in route
_MAX_RADIUS_KM = 60


@dataclass
class RouteStop:
    call_id: str
    elevator_id: str
    address: str
    city: str
    building: str
    fault_type: str
    priority: str
    lat: float
    lng: float
    travel_minutes: int   # from previous stop


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in km between two GPS points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _km_to_minutes(km: float) -> int:
    """Rough driving estimate: km × road-factor 1.3 ÷ 60 km/h."""
    return max(1, int(km * 1.3 / 60 * 60))


def _priority_weight(priority: str) -> int:
    """Lower number = higher urgency (used as tiebreaker)."""
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(priority, 2)


def build_route(
    db: Session,
    technician: Technician,
    include_unassigned: bool = True,
) -> list[RouteStop]:
    """
    Build an optimized ordered route for a technician from their current position.

    Includes:
      - Calls already CONFIRMED/ASSIGNED to this technician
      - Unassigned OPEN calls within _MAX_RADIUS_KM (if include_unassigned=True)

    Returns ordered list of RouteStop (nearest-neighbor order).
    """
    tech_lat = technician.current_latitude
    tech_lng = technician.current_longitude
    if not tech_lat or not tech_lng:
        logger.warning("Technician %s has no GPS — cannot build route", technician.name)
        return []

    # ── Collect candidate calls ───────────────────────────────────────────────
    candidates: list[dict] = []

    # 1. Calls already assigned to this technician
    assigned_call_ids = {
        a.service_call_id
        for a in db.query(Assignment)
        .filter(
            Assignment.technician_id == technician.id,
            Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]),
        )
        .all()
    }
    for call_id in assigned_call_ids:
        call = db.query(ServiceCall).filter(ServiceCall.id == call_id).first()
        if call and call.status in ("OPEN", "ASSIGNED", "IN_PROGRESS"):
            candidates.append({"call": call, "assigned": True})

    # 2. Unassigned OPEN calls nearby
    if include_unassigned:
        assigned_globally = {
            a.service_call_id
            for a in db.query(Assignment)
            .filter(Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]))
            .all()
        }
        open_calls = (
            db.query(ServiceCall)
            .filter(ServiceCall.status == "OPEN")
            .all()
        )
        for call in open_calls:
            if call.id in assigned_globally or call.id in assigned_call_ids:
                continue
            elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
            if not elevator:
                continue
            lat, lng = ensure_elevator_coords(db, elevator)
            dist_km = _haversine_km(tech_lat, tech_lng, lat, lng)
            if dist_km <= _MAX_RADIUS_KM:
                candidates.append({"call": call, "assigned": False})

    if not candidates:
        return []

    # ── Nearest-neighbor ordering ────────────────────────────────────────────
    # Resolve coords for all candidates
    stops_pool: list[dict] = []
    for item in candidates:
        call = item["call"]
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if not elevator:
            continue
        lat, lng = ensure_elevator_coords(db, elevator)
        stops_pool.append({
            "call": call,
            "elevator": elevator,
            "lat": lat,
            "lng": lng,
            "assigned": item["assigned"],
        })

    ordered: list[RouteStop] = []
    visited = set()
    cur_lat, cur_lng = tech_lat, tech_lng

    while len(visited) < len(stops_pool):
        best_idx  = None
        best_dist = float("inf")

        for i, stop in enumerate(stops_pool):
            if i in visited:
                continue
            # CRITICAL calls always jump to front
            if stop["call"].priority == "CRITICAL" and best_idx is None:
                best_idx = i
                best_dist = _haversine_km(cur_lat, cur_lng, stop["lat"], stop["lng"])
                continue
            dist = _haversine_km(cur_lat, cur_lng, stop["lat"], stop["lng"])
            # Weight by priority so CRITICAL/HIGH bubble up when distances are similar
            score = dist + _priority_weight(stop["call"].priority) * 2
            if score < best_dist:
                best_dist = score
                best_idx  = i

        if best_idx is None:
            break

        stop = stops_pool[best_idx]
        visited.add(best_idx)

        km = _haversine_km(cur_lat, cur_lng, stop["lat"], stop["lng"])
        minutes = _km_to_minutes(km)

        _FAULT_HE = {
            "STUCK": "מעלית תקועה 🚨", "DOOR": "תקלת דלת",
            "ELECTRICAL": "חשמלית", "MECHANICAL": "מכנית",
            "SOFTWARE": "תוכנה", "OTHER": "כללית",
        }

        ordered.append(RouteStop(
            call_id=str(stop["call"].id),
            elevator_id=str(stop["elevator"].id),
            address=stop["elevator"].address,
            city=stop["elevator"].city,
            building=stop["elevator"].building_name or "",
            fault_type=_FAULT_HE.get(stop["call"].fault_type, stop["call"].fault_type),
            priority=stop["call"].priority,
            lat=stop["lat"],
            lng=stop["lng"],
            travel_minutes=minutes,
        ))
        cur_lat, cur_lng = stop["lat"], stop["lng"]

    return ordered


def format_route_message(technician_name: str, stops: list[RouteStop]) -> str:
    """Format the ordered route as a WhatsApp message with a Google Maps link."""
    if not stops:
        return f"בוקר טוב {technician_name}! אין קריאות פתוחות באזורך כרגע 👍"

    _PRI_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

    lines = [f"🗺️ *המסלול שלך להיום, {technician_name}*", "────────────────────"]

    total_minutes = 0
    for i, stop in enumerate(stops, 1):
        pri_emoji = _PRI_EMOJI.get(stop.priority, "⚪")
        building  = f" ({stop.building})" if stop.building else ""
        lines.append(
            f"{i}. {pri_emoji} *{stop.address}, {stop.city}*{building}\n"
            f"   🔧 {stop.fault_type}\n"
            f"   🚗 ~{stop.travel_minutes} דק' מהתחנה הקודמת"
        )
        total_minutes += stop.travel_minutes

    lines.append("────────────────────")
    lines.append(f"📍 סה\"כ {len(stops)} קריאות | ~{total_minutes} דקות נסיעה")

    # Google Maps link with all waypoints
    if len(stops) == 1:
        maps_url = f"https://maps.google.com/?q={stops[0].lat},{stops[0].lng}"
    else:
        waypoints = "|".join(f"{s.lat},{s.lng}" for s in stops[1:-1])
        origin      = f"{stops[0].lat},{stops[0].lng}"
        destination = f"{stops[-1].lat},{stops[-1].lng}"
        maps_url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={origin}"
            f"&destination={destination}"
            f"&waypoints={waypoints}"
            f"&travelmode=driving"
        )

    lines.append(f"\n🔗 [פתח מסלול ב-Google Maps]({maps_url})")
    return "\n".join(lines)


def send_route_to_technician(db: Session, technician: Technician) -> bool:
    """Build and send the daily route WhatsApp to a technician."""
    from app.services.whatsapp_service import _send_message

    phone = technician.whatsapp_number or technician.phone
    if not phone:
        return False

    stops = build_route(db, technician)
    msg   = format_route_message(technician.name, stops)
    sent  = _send_message(phone, msg)

    if sent:
        logger.info("🗺️ Route sent to %s (%d stops)", technician.name, len(stops))
    return sent


def notify_technician_new_stop(
    db: Session,
    technician: Technician,
    new_call: ServiceCall,
) -> bool:
    """
    Called when a new call is added to a technician already on a route.
    Sends an updated route message.
    """
    from app.services.whatsapp_service import _send_message

    phone = technician.whatsapp_number or technician.phone
    if not phone:
        return False

    elevator = db.query(Elevator).filter(Elevator.id == new_call.elevator_id).first()
    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

    # Send quick alert + full updated route
    _send_message(
        phone,
        f"📢 *קריאה חדשה נוספה למסלולך*\n📍 {addr}\n\nמסלול מעודכן:"
    )
    return send_route_to_technician(db, technician)
