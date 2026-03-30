"""
AI Assignment Agent
===================
Selects the best technician for a service call using:
  - Real travel time (Google Maps Distance Matrix)
  - Current workload (open assigned calls)
  - Technician availability
  - Fault-type specialization match

Flow
----
1. Geocode elevator address if not yet cached.
2. For each available technician, compute a weighted score.
3. Send a WhatsApp confirmation request to the top candidate.
4. Create a PENDING_CONFIRMATION assignment record.
5. When the technician replies (via /webhooks/whatsapp), the assignment
   is either CONFIRMED or the next candidate is tried.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.assignment import Assignment, AuditLog
from app.models.elevator import Elevator
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.services import maps_service, whatsapp_service

logger = logging.getLogger(__name__)

# Base coordinates for technician home cities (used before GPS is shared)
_CITY_FALLBACK = maps_service.CITY_COORDS

# Fault → required specialization
_FAULT_SPEC = {
    "MECHANICAL": "MECHANICAL",
    "ELECTRICAL": "ELECTRICAL",
    "SOFTWARE":   "SOFTWARE",
    "STUCK":      "MECHANICAL",
    "DOOR":       "MECHANICAL",
}

# Priority → travel-time weight (higher urgency → distance matters more)
_PRIORITY_TRAVEL_WEIGHT = {
    "CRITICAL": 0.75,
    "HIGH":     0.65,
    "MEDIUM":   0.50,
    "LOW":      0.40,
}


@dataclass
class CandidateScore:
    technician: Technician
    travel_minutes: int
    daily_calls: int
    score: float          # lower = better


def _tech_location(tech: Technician) -> tuple[float, float]:
    """Return the technician's best available coordinates."""
    if tech.current_latitude and tech.current_longitude:
        return tech.current_latitude, tech.current_longitude
    if tech.base_latitude and tech.base_longitude:
        return tech.base_latitude, tech.base_longitude
    # Fallback: parse city from area_codes or use Afula as default
    return _CITY_FALLBACK.get("עפולה", (32.6080, 35.2896))


def _daily_calls(db: Session, tech_id: uuid.UUID) -> int:
    """Count assignments for today (all statuses except CANCELLED/REJECTED)."""
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    return (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech_id,
            Assignment.assigned_at >= today_start,
            Assignment.status.notin_(["REJECTED", "CANCELLED"]),
        )
        .count()
    )


def _score_candidate(
    travel_minutes: int,
    daily_calls: int,
    max_daily: int,
    has_specialization: bool,
    priority: str,
) -> float:
    """
    Weighted score — lower is better.

    Weights depend on call priority:
      travel_weight  = 40–75 %
      workload_weight = 25–60 %
    Specialization mismatch adds +30 penalty points.
    """
    travel_weight   = _PRIORITY_TRAVEL_WEIGHT.get(priority, 0.55)
    workload_weight = 1.0 - travel_weight

    travel_norm   = min(travel_minutes / 120, 1.0)   # cap at 2 h
    workload_norm = min(daily_calls / max(max_daily, 1), 1.0)

    score = travel_weight * travel_norm + workload_weight * workload_norm
    if not has_specialization:
        score += 0.30
    return round(score, 4)


def rank_technicians(
    db: Session,
    elevator: Elevator,
    fault_type: str,
    priority: str,
) -> list[CandidateScore]:
    """
    Return all available technicians sorted by score (best first).
    """
    elev_lat, elev_lng = maps_service.ensure_elevator_coords(db, elevator)
    required_spec = _FAULT_SPEC.get(fault_type)

    candidates = (
        db.query(Technician)
        .filter(Technician.is_active == True, Technician.is_available == True)  # noqa: E712
        .all()
    )

    scored: list[CandidateScore] = []
    for tech in candidates:
        daily = _daily_calls(db, tech.id)
        if daily >= tech.max_daily_calls:
            continue

        origin_lat, origin_lng = _tech_location(tech)
        travel = maps_service.travel_time_minutes(origin_lat, origin_lng, elev_lat, elev_lng)

        specs = tech.specializations or []
        has_spec = (required_spec is None) or (required_spec in specs)

        score = _score_candidate(travel, daily, tech.max_daily_calls, has_spec, priority)
        scored.append(CandidateScore(tech, travel, daily, score))

    scored.sort(key=lambda c: c.score)
    return scored


def assign_with_confirmation(
    db: Session,
    service_call: ServiceCall,
) -> Optional[Assignment]:
    """
    Main entry point called after a service call is created.

    1. Ranks available technicians.
    2. Creates a PENDING_CONFIRMATION assignment for the top candidate.
    3. Sends a WhatsApp message asking for acceptance.
    4. Returns the Assignment (or None if no candidate is available).
    """
    elevator = db.query(Elevator).filter(Elevator.id == service_call.elevator_id).first()
    if not elevator:
        logger.error("Elevator %s not found for assignment", service_call.elevator_id)
        return None

    candidates = rank_technicians(db, elevator, service_call.fault_type, service_call.priority)

    if not candidates:
        logger.warning("No available technicians for call %s", service_call.id)
        return None

    best = candidates[0]
    tech = best.technician

    # Create PENDING_CONFIRMATION assignment
    assignment = Assignment(
        service_call_id=service_call.id,
        technician_id=tech.id,
        assignment_type="AUTO",
        status="PENDING_CONFIRMATION",
        travel_minutes=best.travel_minutes,
        notes=(
            f"AI recommendation | score={best.score:.3f} | "
            f"travel={best.travel_minutes}min | calls_today={best.daily_calls}"
        ),
    )
    db.add(assignment)
    db.flush()

    # Update call status
    service_call.status = "ASSIGNED"
    service_call.assigned_at = datetime.now(timezone.utc)

    audit = AuditLog(
        service_call_id=service_call.id,
        changed_by="ai_agent",
        old_status="OPEN",
        new_status="ASSIGNED",
        notes=f"AI assigned to {tech.name} — pending confirmation",
    )
    db.add(audit)
    db.commit()
    db.refresh(assignment)

    # Send WhatsApp notification
    phone = tech.whatsapp_number or tech.phone
    if phone:
        sent = whatsapp_service.notify_technician_new_call(
            phone=phone,
            technician_name=tech.name,
            call_id=str(service_call.id),
            address=elevator.address,
            city=elevator.city,
            fault_type=service_call.fault_type,
            priority=service_call.priority,
            caller_name=_extract_caller(service_call.reported_by),
            caller_phone=_extract_phone(service_call.reported_by),
            travel_minutes=best.travel_minutes,
        )
        if sent:
            logger.info("WhatsApp sent to %s (%s)", tech.name, phone)
        else:
            logger.warning("WhatsApp failed for %s — assignment pending anyway", tech.name)
    else:
        logger.warning("Technician %s has no phone — WhatsApp skipped", tech.name)

    return assignment


def confirm_assignment(db: Session, technician_phone: str) -> Optional[Assignment]:
    """
    Called when a technician sends "1" via WhatsApp.
    Finds their latest PENDING_CONFIRMATION assignment and confirms it.
    """
    tech = _find_tech_by_phone(db, technician_phone)
    if not tech:
        return None

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        return None

    assignment.status = "CONFIRMED"

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if call:
        audit = AuditLog(
            service_call_id=call.id,
            changed_by=tech.email,
            old_status="ASSIGNED",
            new_status="IN_PROGRESS",
            notes=f"{tech.name} אישר קבלת הקריאה — בדרך ({assignment.travel_minutes or '?'} דק׳)",
        )
        call.status = "IN_PROGRESS"  # stays here until technician files report
        db.add(audit)

    # Send confirmation back to technician
    from app.services.whatsapp_service import _send_message
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
    if elevator:
        _send_message(
            tech.whatsapp_number or tech.phone,
            f"✅ קיבלת את הקריאה!\n"
            f"📍 {elevator.address}, {elevator.city}\n"
            f"🚗 זמן נסיעה: ~{assignment.travel_minutes or '?'} דקות\n\n"
            f"בסיום הטיפול, שלח *דוח* כדי לסגור את הקריאה."
        )

    db.commit()
    db.refresh(assignment)
    return assignment


def reject_assignment(db: Session, technician_phone: str) -> Optional[Assignment]:
    """
    Called when a technician sends "2" via WhatsApp.
    Marks the assignment as REJECTED and tries the next-best candidate.
    """
    tech = _find_tech_by_phone(db, technician_phone)
    if not tech:
        return None

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .order_by(Assignment.assigned_at.desc())
        .first()
    )
    if not assignment:
        return None

    assignment.status = "REJECTED"

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if call:
        audit = AuditLog(
            service_call_id=call.id,
            changed_by=tech.email,
            old_status="ASSIGNED",
            new_status="OPEN",
            notes=f"{tech.name} דחה את הקריאה — מחפש טכנאי אחר",
        )
        call.status = "OPEN"
        db.add(audit)
        db.commit()

        # Try to assign the next available technician (excluding the rejecter)
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if elevator:
            candidates = rank_technicians(db, elevator, call.fault_type, call.priority)
            # Filter out the technician who just rejected
            candidates = [c for c in candidates if c.technician.id != tech.id]
            if candidates:
                next_assignment = assign_with_confirmation(db, call)
                return next_assignment

    db.commit()
    return assignment


# ── Private helpers ───────────────────────────────────────────────────────────

def _find_tech_by_phone(db: Session, phone: str) -> Optional[Technician]:
    """Look up a technician by phone or WhatsApp number."""
    digits = "".join(c for c in phone if c.isdigit())
    # Normalize: strip leading 972 or 0
    if digits.startswith("972"):
        digits = "0" + digits[3:]

    return (
        db.query(Technician)
        .filter(
            (Technician.phone.contains(digits[-9:])) |
            (Technician.whatsapp_number.contains(digits[-9:]))
        )
        .first()
    )


def _extract_caller(reported_by: str) -> str:
    """Extract caller name from reported_by field (may contain name + phone)."""
    if "|" in reported_by:
        return reported_by.split("|")[0].replace("דיווח מ:", "").strip()
    return reported_by


def _extract_phone(reported_by: str) -> str:
    """Extract phone number from reported_by field."""
    if "טל׳:" in reported_by:
        return reported_by.split("טל׳:")[-1].strip()
    return ""
