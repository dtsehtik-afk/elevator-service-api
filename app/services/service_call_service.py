"""Business logic for service call management."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.assignment import AuditLog
from app.models.service_call import ServiceCall
from app.schemas.service_call import ServiceCallCreate, ServiceCallUpdate
from app.services.elevator_service import calculate_risk_score


def _upsert_caller_contact(db: Session, elevator, reported_by: str) -> None:
    """Save caller info as a Contact on the elevator's building (auto_added=True).

    reported_by format can be: "שם | 0501234567", "0501234567", or plain name.
    Skips if no phone can be extracted or reported_by is a system token.
    """
    if not reported_by or reported_by.startswith("system"):
        return
    from app.models.contact import Contact

    # Parse name and phone from "name | phone" or "phone" formats
    phone, name = None, reported_by.strip()
    if "|" in reported_by:
        parts = [p.strip() for p in reported_by.split("|", 1)]
        # figure out which part is the phone
        for part in parts:
            cleaned = part.replace("-", "").replace(" ", "").replace("+", "")
            if cleaned.isdigit() and len(cleaned) >= 7:
                phone = part.strip()
            else:
                name = part.strip()
    else:
        cleaned = reported_by.replace("-", "").replace(" ", "").replace("+", "")
        if cleaned.isdigit() and len(cleaned) >= 7:
            phone = reported_by.strip()
            name = reported_by.strip()

    if not phone:
        return  # no identifiable phone — skip

    elevator_id = getattr(elevator, "id", None)
    if not elevator_id:
        return

    # Check if this phone is already a contact on this elevator
    existing = db.query(Contact).filter(
        Contact.phone == phone,
        Contact.elevator_id == elevator_id,
    ).first()

    if existing:
        if name and name != phone and existing.name == phone:
            existing.name = name
            db.commit()
        return

    contact = Contact(
        elevator_id=elevator_id,
        building_id=getattr(elevator, "building_id", None),
        name=name or phone,
        phone=phone,
        role="RESIDENT",
        auto_added=True,
    )
    db.add(contact)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _check_recurring(db: Session, elevator_id: uuid.UUID, fault_type: str) -> bool:
    """Return True if the same fault_type appeared on this elevator in the last 30 days."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    existing = (
        db.query(ServiceCall)
        .filter(
            ServiceCall.elevator_id == elevator_id,
            ServiceCall.fault_type == fault_type,
            ServiceCall.created_at >= thirty_days_ago,
        )
        .first()
    )
    return existing is not None


def create_service_call(
    db: Session, data: ServiceCallCreate, current_user_email: str
) -> ServiceCall:
    """Open a new service call.

    Automatically:
    - Marks ``is_recurring=True`` if the same fault_type appeared in the last 30 days.
    - Updates the elevator's risk_score.
    - Triggers auto-assignment for CRITICAL priority calls.

    Args:
        db: Database session.
        data: Validated service call creation data.
        current_user_email: Email of the user opening the call (for audit log).

    Returns:
        The newly created ServiceCall ORM object.
    """
    is_recurring = _check_recurring(db, data.elevator_id, data.fault_type)

    _sla_hours = {"CRITICAL": 4, "HIGH": 8, "MEDIUM": 24, "LOW": 72}
    sla_deadline = datetime.now(timezone.utc) + timedelta(hours=_sla_hours.get(data.priority, 24))

    call = ServiceCall(
        elevator_id=data.elevator_id,
        reported_by=data.reported_by,
        description=data.description,
        priority=data.priority,
        fault_type=data.fault_type,
        is_recurring=is_recurring,
        sla_deadline=sla_deadline,
    )
    db.add(call)
    db.flush()  # Get the ID before commit

    # Write initial audit log
    audit = AuditLog(
        service_call_id=call.id,
        changed_by=current_user_email,
        old_status=None,
        new_status="OPEN",
        notes="Service call created",
    )
    db.add(audit)

    db.commit()
    db.refresh(call)

    # Update elevator risk score
    new_score = calculate_risk_score(db, data.elevator_id)
    from app.models.elevator import Elevator
    elevator = db.query(Elevator).filter(Elevator.id == data.elevator_id).first()
    if elevator:
        elevator.risk_score = new_score
        db.commit()
        # Auto-save caller as Contact on the elevator's building
        _upsert_caller_contact(db, elevator, data.reported_by)

    # If there's a MONITORING call for the same elevator, close it and mark new call recurring
    monitoring_call = (
        db.query(ServiceCall)
        .filter(
            ServiceCall.elevator_id == data.elevator_id,
            ServiceCall.status == "MONITORING",
            ServiceCall.id != call.id,
        )
        .first()
    )
    if monitoring_call:
        call.is_recurring = True
        if call.priority in ("LOW", "MEDIUM"):
            call.priority = "HIGH"
        monitoring_call.status = "CLOSED"
        db.add(AuditLog(
            service_call_id=monitoring_call.id,
            changed_by="system",
            old_status="MONITORING",
            new_status="CLOSED",
            notes="נסגרה — תקלה חוזרת נפתחה",
        ))
        db.add(AuditLog(
            service_call_id=call.id,
            changed_by=current_user_email,
            old_status="OPEN",
            new_status="OPEN",
            notes="סומנה כתקלה חוזרת — עדיפות עודכנה ל-HIGH",
        ))
        db.commit()
        db.refresh(call)

    # Auto-assign CRITICAL calls
    if data.priority == "CRITICAL":
        from app.services.assignment_service import auto_assign_call
        try:
            auto_assign_call(db, call.id, current_user_email)
            db.refresh(call)
        except Exception as exc:
            logger.error("Auto-assignment failed for CRITICAL call %s: %s", call.id, exc, exc_info=True)

    return call


def get_service_call(db: Session, call_id: uuid.UUID) -> Optional[ServiceCall]:
    """Fetch a service call by its UUID."""
    return db.query(ServiceCall).filter(ServiceCall.id == call_id).first()


def list_service_calls(
    db: Session,
    elevator_id: Optional[uuid.UUID] = None,
    customer_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    fault_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[ServiceCall]:
    """Return a filtered list of service calls."""
    from app.models.elevator import Elevator
    query = db.query(ServiceCall)
    if elevator_id:
        query = query.filter(ServiceCall.elevator_id == elevator_id)
    if customer_id:
        query = query.join(Elevator, ServiceCall.elevator_id == Elevator.id).filter(
            Elevator.customer_id == customer_id
        )
    if status:
        statuses = [s.strip() for s in status.split(',') if s.strip()]
        if len(statuses) == 1:
            query = query.filter(ServiceCall.status == statuses[0])
        else:
            query = query.filter(ServiceCall.status.in_(statuses))
    if priority:
        query = query.filter(ServiceCall.priority == priority)
    if fault_type:
        query = query.filter(ServiceCall.fault_type == fault_type)
    return query.order_by(ServiceCall.created_at.desc()).offset(skip).limit(min(limit, 1000)).all()


def update_service_call(
    db: Session,
    call_id: uuid.UUID,
    data: ServiceCallUpdate,
    current_user_email: str,
) -> Optional[ServiceCall]:
    """Apply partial updates to a service call and write an audit log entry.

    Automatically sets ``resolved_at`` when status changes to RESOLVED.

    Returns:
        Updated ServiceCall or None if not found.
    """
    call = get_service_call(db, call_id)
    if not call:
        return None

    old_status = call.status

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(call, field, value)

    if data.status in ("RESOLVED", "CLOSED") and not call.resolved_at:
        call.resolved_at = datetime.now(timezone.utc)
    if data.status in ("RESOLVED", "CLOSED") and not call.resolved_by:
        call.resolved_by = current_user_email

    if data.status and data.status != old_status:
        audit = AuditLog(
            service_call_id=call_id,
            changed_by=current_user_email,
            old_status=old_status,
            new_status=data.status,
        )
        db.add(audit)

        # When a MAINTENANCE call is resolved/closed, advance elevator's next service date
        if data.status in ("RESOLVED", "CLOSED") and call.fault_type == "MAINTENANCE":
            _advance_next_service_date(db, call.elevator_id)

    db.commit()
    db.refresh(call)
    return call


def _next_working_day(d: "date_type") -> "date_type":
    """Advance date past Saturday (Israeli day off)."""
    from datetime import date as date_type
    while d.weekday() == 5:  # 5 = Saturday
        d += timedelta(days=1)
    return d


def _advance_next_service_date(db: Session, elevator_id: uuid.UUID) -> None:
    """After a MAINTENANCE service call is completed, compute and store the next service date."""
    from datetime import date as _date
    from app.models.elevator import Elevator
    elev = db.query(Elevator).filter(Elevator.id == elevator_id).first()
    if not elev:
        return
    times_per_year = elev.maintenance_times_per_year or 6
    interval_days = round(365 / times_per_year)
    base = _date.today()
    next_date = _next_working_day(base + timedelta(days=interval_days))
    elev.last_service_date = base
    elev.next_service_date = next_date
