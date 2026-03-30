"""Business logic for service call management."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.assignment import AuditLog
from app.models.service_call import ServiceCall
from app.schemas.service_call import ServiceCallCreate, ServiceCallUpdate
from app.services.elevator_service import calculate_risk_score


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

    call = ServiceCall(
        elevator_id=data.elevator_id,
        reported_by=data.reported_by,
        description=data.description,
        priority=data.priority,
        fault_type=data.fault_type,
        is_recurring=is_recurring,
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

    # Auto-assign CRITICAL calls
    if data.priority == "CRITICAL":
        from app.services.assignment_service import auto_assign_call
        try:
            auto_assign_call(db, call.id, current_user_email)
            db.refresh(call)
        except Exception:
            pass  # Log but don't fail the call creation

    return call


def get_service_call(db: Session, call_id: uuid.UUID) -> Optional[ServiceCall]:
    """Fetch a service call by its UUID."""
    return db.query(ServiceCall).filter(ServiceCall.id == call_id).first()


def list_service_calls(
    db: Session,
    elevator_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    fault_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[ServiceCall]:
    """Return a filtered list of service calls.

    Args:
        db: Database session.
        elevator_id: Filter by elevator.
        status: Filter by status.
        priority: Filter by priority.
        fault_type: Filter by fault type.
        skip: Pagination offset.
        limit: Page size.

    Returns:
        List of ServiceCall objects.
    """
    query = db.query(ServiceCall)
    if elevator_id:
        query = query.filter(ServiceCall.elevator_id == elevator_id)
    if status:
        query = query.filter(ServiceCall.status == status)
    if priority:
        query = query.filter(ServiceCall.priority == priority)
    if fault_type:
        query = query.filter(ServiceCall.fault_type == fault_type)
    return query.order_by(ServiceCall.created_at.desc()).offset(skip).limit(min(limit, 200)).all()


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

    if data.status == "RESOLVED" and not call.resolved_at:
        call.resolved_at = datetime.now(timezone.utc)

    if data.status and data.status != old_status:
        audit = AuditLog(
            service_call_id=call_id,
            changed_by=current_user_email,
            old_status=old_status,
            new_status=data.status,
        )
        db.add(audit)

    db.commit()
    db.refresh(call)
    return call
