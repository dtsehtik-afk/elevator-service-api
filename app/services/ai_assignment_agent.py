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
from app.services.working_hours import is_working_hours

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

    if is_working_hours():
        candidates = (
            db.query(Technician)
            .filter(Technician.is_active == True, Technician.is_available == True)  # noqa: E712
            .all()
        )
    else:
        # Outside working hours — only the on-call technician
        candidates = (
            db.query(Technician)
            .filter(Technician.is_active == True, Technician.is_on_call == True)  # noqa: E712
            .all()
        )

    # Preload last-visit times for tie-breaking (technician who last visited this elevator gets priority)
    from app.models.assignment import Assignment as _Assignment
    last_visit: dict = {}
    if elevator:
        visits = (
            db.query(_Assignment.technician_id, _Assignment.assigned_at)
            .filter(
                _Assignment.service_call_id.in_(
                    db.query(ServiceCall.id).filter(ServiceCall.elevator_id == elevator.id)
                ),
                _Assignment.status.in_(["CONFIRMED", "AUTO_ASSIGNED"]),
            )
            .all()
        )
        for tech_id, visited_at in visits:
            if tech_id not in last_visit or visited_at > last_visit[tech_id]:
                last_visit[tech_id] = visited_at

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

    # Sort: primary = score (lower=better), tie-break = last visited this elevator (more recent=better)
    import datetime as _dt
    scored.sort(key=lambda c: (
        c.score,
        -(last_visit.get(c.technician.id, _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)).timestamp()),
    ))
    logger.warning(
        "📊 Ranking for call (working_hours=%s): %s",
        is_working_hours(),
        " | ".join(
            f"{c.technician.name} score={c.score:.3f} travel={c.travel_minutes}m calls={c.daily_calls}"
            for c in scored
        ) or "NO CANDIDATES"
    )
    return scored


def _elevator_context(db: Session, elevator_id) -> str:
    """
    Return a short context string about open inspection deficiencies and upcoming
    maintenance for the given elevator — appended to assignment WhatsApp messages.
    """
    from datetime import date, timedelta
    from app.models.inspection_report import InspectionReport

    lines = []

    # Open inspection deficiencies
    open_reports = (
        db.query(InspectionReport)
        .filter(
            InspectionReport.elevator_id == elevator_id,
            InspectionReport.report_status.in_(["OPEN", "PARTIAL"]),
        )
        .all()
    )
    if open_reports:
        total_def = sum(r.deficiency_count or 0 for r in open_reports)
        lines.append(f"⚠️ *ליקויי בודק פתוחים:* {total_def} ליקויים — טפל בדשבורד")

    # Upcoming or overdue maintenance
    elevator = db.query(Elevator).filter(Elevator.id == elevator_id).first()
    if elevator and elevator.next_service_date:
        today = date.today()
        days_left = (elevator.next_service_date - today).days
        if days_left < 0:
            lines.append(f"🔧 *טיפול מונע:* באיחור {-days_left} ימים!")
        elif days_left == 0:
            lines.append("🔧 *טיפול מונע:* מתוכנן להיום!")
        elif days_left <= 15:
            lines.append(f"🔧 *טיפול מונע:* עוד {days_left} ימים")

    return "\n".join(lines)


def assign_with_confirmation(
    db: Session,
    service_call: ServiceCall,
    exclude_tech_ids: list[uuid.UUID] | None = None,
    needs_confirmation: bool = True,
) -> Optional[Assignment]:
    """
    Broadcast model: ALL available technicians receive the call simultaneously.
    The top-ranked technician is marked as recommended in each message.
    First to reply "1" takes the call; others receive a cancellation.
    When needs_confirmation=False (email calls), assigns only top candidate directly.
    Returns the top-ranked Assignment (or None if no candidates).
    """
    elevator = db.query(Elevator).filter(Elevator.id == service_call.elevator_id).first()
    if not elevator:
        logger.error("Elevator %s not found for assignment", service_call.elevator_id)
        return None

    db.refresh(service_call)
    if service_call.status not in ("OPEN", "PENDING"):
        logger.info("Call %s already assigned (status=%s), skipping", service_call.id, service_call.status)
        return None

    candidates = rank_technicians(db, elevator, service_call.fault_type, service_call.priority)

    if exclude_tech_ids:
        candidates = [c for c in candidates if c.technician.id not in exclude_tech_ids]

    if not candidates:
        logger.warning("No available technicians for call %s", service_call.id)
        return None

    caller_name  = _extract_caller(service_call.reported_by)
    caller_phone = _extract_phone(service_call.reported_by)

    if not needs_confirmation:
        # Email-originated: auto-assign top candidate directly (no broadcast)
        best = candidates[0]
        tech = best.technician
        assignment = Assignment(
            service_call_id=service_call.id,
            technician_id=tech.id,
            assignment_type="AUTO",
            status="CONFIRMED",
            travel_minutes=best.travel_minutes,
            notes=f"AI auto-assigned | score={best.score:.3f} | travel={best.travel_minutes}min | auto-confirmed (email call)",
        )
        db.add(assignment)
        service_call.status = "IN_PROGRESS"
        service_call.assigned_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            service_call_id=service_call.id,
            changed_by="ai_agent",
            old_status="OPEN",
            new_status="IN_PROGRESS",
            notes=f"AI auto-assigned to {tech.name} (email call)",
        ))
        db.commit()
        db.refresh(assignment)
        phone = tech.whatsapp_number or tech.phone
        if phone:
            ctx = _elevator_context(db, elevator.id)
            desc = service_call.description or ""
            if ctx:
                desc = f"{desc}\n{ctx}".strip() if desc else ctx
            whatsapp_service.notify_technician_auto_assigned(
                phone=phone,
                technician_name=tech.name,
                address=elevator.address,
                city=elevator.city,
                fault_type=service_call.fault_type,
                priority=service_call.priority,
                caller_name=caller_name,
                caller_phone=caller_phone,
                travel_minutes=best.travel_minutes,
                description=desc,
            )
        return assignment

    # ── Broadcast to ALL available technicians ────────────────────────────────
    recommended_name = candidates[0].technician.name
    first_assignment: Optional[Assignment] = None
    from app.config import get_settings as _gs
    base_url = _gs().app_base_url

    # Cancel any stale pending assignments for this call before new broadcast
    stale = db.query(Assignment).filter(
        Assignment.service_call_id == service_call.id,
        Assignment.status == "PENDING_CONFIRMATION",
    ).all()
    for s in stale:
        s.status = "CANCELLED"
    if stale:
        db.commit()

    for candidate in candidates:
        tech = candidate.technician
        assignment = Assignment(
            service_call_id=service_call.id,
            technician_id=tech.id,
            assignment_type="AUTO",
            status="PENDING_CONFIRMATION",
            travel_minutes=candidate.travel_minutes,
            notes=(
                f"Broadcast | score={candidate.score:.3f} | travel={candidate.travel_minutes}min | "
                f"recommended={recommended_name}"
            ),
        )
        db.add(assignment)
        db.flush()
        if first_assignment is None:
            first_assignment = assignment

        phone = tech.whatsapp_number or tech.phone
        if phone:
            ctx = _elevator_context(db, elevator.id)
            desc = service_call.description or ""
            if ctx:
                desc = f"{desc}\n{ctx}".strip() if desc else ctx
            whatsapp_service.notify_technician_new_call(
                phone=phone,
                technician_name=tech.name,
                call_id=str(service_call.id),
                address=elevator.address,
                city=elevator.city,
                fault_type=service_call.fault_type,
                priority=service_call.priority,
                caller_name=caller_name,
                caller_phone=caller_phone,
                travel_minutes=candidate.travel_minutes,
                description=desc,
                tech_id=str(tech.id),
                recommended_tech_name=recommended_name,
                lat=elevator.latitude,
                lng=elevator.longitude,
            )

    service_call.status = "ASSIGNED"
    service_call.assigned_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        service_call_id=service_call.id,
        changed_by="ai_agent",
        old_status="OPEN",
        new_status="ASSIGNED",
        notes=f"Broadcast to {len(candidates)} technicians — recommended: {recommended_name}",
    ))
    db.commit()

    tech_names = ", ".join(c.technician.name for c in candidates)
    whatsapp_service.notify_dispatcher(
        f"📋 קריאה שודרה ל-{len(candidates)} טכנאים: {tech_names}\n"
        f"📍 {elevator.address}, {elevator.city}\n"
        f"⭐ מומלץ: *{recommended_name}*"
    )

    return first_assignment


def confirm_assignment(db: Session, technician_phone: str) -> Optional[Assignment]:
    """
    Called when a technician sends "1" via WhatsApp.
    Finds their latest PENDING_CONFIRMATION assignment and confirms it.
    """
    from app.services.whatsapp_service import _send_message

    tech = _find_tech_by_phone(db, technician_phone)
    if not tech:
        logger.warning("confirm_assignment: technician not found for %s", technician_phone)
        return None

    phone_out = tech.whatsapp_number or tech.phone

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .order_by(Assignment.assigned_at.asc())
        .first()
    )
    if not assignment:
        _send_message(phone_out,
                      "ℹ️ אין קריאה פעילה הממתינה לאישורך כרגע.")
        return None

    assignment.status = "CONFIRMED"

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None

    if call:
        audit = AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status="ASSIGNED",
            new_status="IN_PROGRESS",
            notes=f"{tech.name} אישר קבלת הקריאה — בדרך ({assignment.travel_minutes or '?'} דק׳)",
        )
        call.status = "IN_PROGRESS"
        db.add(audit)

    # Cancel all other PENDING_CONFIRMATION assignments for this call
    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"
    other_pending = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status == "PENDING_CONFIRMATION",
        Assignment.id != assignment.id,
    ).all()
    for other in other_pending:
        other.status = "CANCELLED"
        other_tech = db.query(Technician).filter(Technician.id == other.technician_id).first()
        if other_tech:
            other_phone = other_tech.whatsapp_number or other_tech.phone
            if other_phone:
                whatsapp_service.notify_call_taken_by_other(other_phone, elevator.address if elevator else "", elevator.city if elevator else "", tech.name)
    db.commit()
    db.refresh(assignment)

    # Confirmation message back to technician
    whatsapp_service.notify_dispatcher(f"✅ *{tech.name}* אישר קבלת הקריאה ב{addr}")
    from app.config import get_settings as _gs2
    base_url = getattr(_gs2(), "app_base_url", "").rstrip("/")
    tech_portal = f"{base_url}/app/tech/{tech.id}" if base_url else ""
    _send_message(
        phone_out,
        f"✅ *קיבלת את הקריאה!*\n"
        f"────────────────────\n"
        f"📍 {addr}\n"
        f"🚗 זמן נסיעה: ~{assignment.travel_minutes or '?'} דקות\n"
        f"{whatsapp_service._nav_links(elevator.address if elevator else addr, elevator.city if elevator else '', elevator.latitude if elevator else None, elevator.longitude if elevator else None)}\n"
        + (f"📱 ממשק טכנאי:\n{tech_portal}\n" if tech_portal else "")
        + f"────────────────────\n"
        f"בסיום הטיפול שלח: *דוח* + תיאור קצר"
    )

    # If technician is already in the field with GPS, send updated route
    if tech.current_latitude and tech.current_longitude:
        try:
            from app.services.route_service import send_route_to_technician
            send_route_to_technician(db, tech)
        except Exception as exc:
            logger.error("Route update failed for %s: %s", tech.name, exc)

    logger.info("✅ %s confirmed assignment for call %s", tech.name, call.id if call else "?")
    return assignment


def reject_assignment(db: Session, technician_phone: str) -> Optional[Assignment]:
    """
    Called when a technician sends "2" via WhatsApp.
    Marks the assignment as REJECTED and tries the next-best candidate.
    """
    from app.services.whatsapp_service import _send_message

    tech = _find_tech_by_phone(db, technician_phone)
    if not tech:
        logger.warning("reject_assignment: technician not found for %s", technician_phone)
        return None

    phone_out = tech.whatsapp_number or tech.phone

    assignment = (
        db.query(Assignment)
        .filter(
            Assignment.technician_id == tech.id,
            Assignment.status == "PENDING_CONFIRMATION",
        )
        .order_by(Assignment.assigned_at.asc())
        .first()
    )
    if not assignment:
        _send_message(phone_out,
                      "ℹ️ אין קריאה פעילה הממתינה לתגובתך כרגע.")
        return None

    assignment.status = "REJECTED"
    _send_message(phone_out, "↩️ הקריאה נדחתה.")

    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if call:
        _rej_elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        _rej_addr = f"{_rej_elevator.address}, {_rej_elevator.city}" if _rej_elevator else "כתובת לא ידועה"
        whatsapp_service.notify_dispatcher(f"↩️ *{tech.name}* דחה את הקריאה ב{_rej_addr}")
        db.add(AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status="ASSIGNED",
            new_status="ASSIGNED",
            notes=f"{tech.name} דחה את הקריאה (broadcast — ממתין לאישור אחר)",
        ))
        db.commit()

        # Check if ALL broadcasts for this call were rejected → alert dispatcher
        all_assignments = db.query(Assignment).filter(
            Assignment.service_call_id == call.id,
            Assignment.status.in_(["PENDING_CONFIRMATION", "CONFIRMED", "AUTO_ASSIGNED"]),
        ).count()
        if all_assignments == 0:
            call.status = "OPEN"
            db.commit()
            from app.config import get_settings
            s = get_settings()
            if _rej_elevator:
                whatsapp_service.notify_dispatcher(
                    f"⚠️ *כל הטכנאים דחו* את הקריאה ב{_rej_addr} — נא לשבץ ידנית."
                )

    db.commit()
    return assignment


def get_pending_assignments_for_phone(db: Session, phone: str) -> list:
    """
    Return all PENDING_CONFIRMATION assignments for a technician (by phone).
    Each item: {"assignment_id": str, "address": str, "city": str}
    """
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return []
    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == tech.id,
                Assignment.status == "PENDING_CONFIRMATION")
        .order_by(Assignment.assigned_at.asc())
        .all()
    )
    result = []
    for a in assignments:
        call = db.query(ServiceCall).filter(ServiceCall.id == a.service_call_id).first()
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
        result.append({
            "assignment_id": str(a.id),
            "address": elevator.address if elevator else "",
            "city": elevator.city if elevator else "",
            "assigned_at": a.assigned_at,
        })
    return result


def confirm_assignment_by_id(db: Session, phone: str, assignment_id: str) -> Optional[Assignment]:
    """Confirm a specific assignment by its ID."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return None
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.technician_id == tech.id,
        Assignment.status == "PENDING_CONFIRMATION",
    ).first()
    if not assignment:
        return None

    from app.services.whatsapp_service import _send_message
    assignment.status = "CONFIRMED"
    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first() if call else None
    if call:
        call.status = "IN_PROGRESS"
        db.add(AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status="ASSIGNED", new_status="IN_PROGRESS",
            notes=f"{tech.name} אישר קבלת הקריאה",
        ))
    db.commit()

    addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"

    # Cancel all other PENDING_CONFIRMATION for this call
    other_pending2 = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status == "PENDING_CONFIRMATION",
        Assignment.id != assignment.id,
    ).all()
    for other2 in other_pending2:
        other2.status = "CANCELLED"
        ot2 = db.query(Technician).filter(Technician.id == other2.technician_id).first()
        if ot2:
            op2 = ot2.whatsapp_number or ot2.phone
            if op2:
                whatsapp_service.notify_call_taken_by_other(op2, elevator.address if elevator else "", elevator.city if elevator else "", tech.name)
    db.commit()

    from app.config import get_settings as _gs3
    _base3 = getattr(_gs3(), "app_base_url", "").rstrip("/")
    _portal3 = f"{_base3}/app/tech/{tech.id}" if _base3 else ""
    phone_out = tech.whatsapp_number or tech.phone
    _send_message(phone_out,
        f"✅ *קיבלת את הקריאה!*\n"
        f"📍 {addr}\n"
        f"🚗 ~{assignment.travel_minutes or '?'} דקות\n"
        f"{whatsapp_service._nav_links(elevator.address if elevator else addr, elevator.city if elevator else '', elevator.latitude if elevator else None, elevator.longitude if elevator else None)}\n"
        + (f"📱 ממשק טכנאי:\n{_portal3}\n" if _portal3 else "")
        + f"בסיום שלח: *דוח* + תיאור קצר"
    )
    # Send updated route if technician already has GPS
    if tech.current_latitude and tech.current_longitude:
        try:
            from app.services.route_service import send_route_to_technician
            db.refresh(tech)
            send_route_to_technician(db, tech)
        except Exception as exc:
            logger.error("Route update failed for %s: %s", tech.name, exc)

    logger.info("✅ %s confirmed assignment %s", tech.name, assignment_id)
    return assignment


def reject_assignment_by_id(db: Session, phone: str, assignment_id: str) -> Optional[Assignment]:
    """Reject a specific assignment by its ID and try to reassign."""
    tech = _find_tech_by_phone(db, phone)
    if not tech:
        return None
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.technician_id == tech.id,
        Assignment.status == "PENDING_CONFIRMATION",
    ).first()
    if not assignment:
        return None

    from app.services.whatsapp_service import _send_message
    phone_out = tech.whatsapp_number or tech.phone
    assignment.status = "REJECTED"
    call = db.query(ServiceCall).filter(ServiceCall.id == assignment.service_call_id).first()
    if call:
        elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        addr = f"{elevator.address}, {elevator.city}" if elevator else "כתובת לא ידועה"
        _send_message(phone_out, f"↩️ הקריאה ב{addr} נדחתה — מועברת לטכנאי אחר.")
        whatsapp_service.notify_dispatcher(f"↩️ *{tech.name}* דחה את הקריאה ב{addr} — מועברת הלאה")
        call.status = "OPEN"
        db.add(AuditLog(
            service_call_id=call.id,
            changed_by=tech.email or tech.name,
            old_status="ASSIGNED", new_status="OPEN",
            notes=f"{tech.name} דחה את הקריאה",
        ))
        db.commit()
        rejected_ids = [
            a.technician_id for a in db.query(Assignment).filter(
                Assignment.service_call_id == call.id,
                Assignment.status == "REJECTED",
            ).all()
        ]
        assign_with_confirmation(db, call, exclude_tech_ids=rejected_ids)
    else:
        db.commit()
    logger.info("❌ %s rejected assignment %s", tech.name, assignment_id)
    return assignment


# ── Private helpers ───────────────────────────────────────────────────────────

def _find_tech_by_phone(db: Session, phone: str) -> Optional[Technician]:
    """Look up a technician by phone or WhatsApp number (format-agnostic)."""
    digits = "".join(c for c in phone if c.isdigit())

    # Try last 9 digits (works for 05X, 972X, +972X formats)
    last9 = digits[-9:]

    tech = (
        db.query(Technician)
        .filter(
            (Technician.phone.contains(last9)) |
            (Technician.whatsapp_number.contains(last9))
        )
        .first()
    )

    if not tech:
        logger.warning(
            "⚠️  No technician found for phone '%s' (last9='%s'). "
            "Check that the technician's phone is saved correctly in the DB.",
            phone, last9,
        )
    return tech


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
