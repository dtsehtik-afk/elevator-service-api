"""Router for service call CRUD endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician
from app.schemas.service_call import (
    AuditLogResponse, AssignmentDetailResponse, CallDetailResponse,
    ServiceCallCreate, ServiceCallResponse, ServiceCallUpdate,
)
from app.services import service_call_service

router = APIRouter()


@router.get(
    "",
    response_model=List[ServiceCallResponse],
    summary="List service calls",
    description="Return filtered service calls. Technicians see only their assigned calls.",
)
def list_calls(
    elevator_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None, description="OPEN|ASSIGNED|IN_PROGRESS|RESOLVED|CLOSED"),
    priority: Optional[str] = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW"),
    fault_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """List service calls with optional filters."""
    return service_call_service.list_service_calls(
        db, elevator_id, status, priority, fault_type, skip, limit
    )


@router.post(
    "",
    response_model=ServiceCallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open service call",
    description="Open a new service call. Automatically detects recurring faults and auto-assigns CRITICAL calls.",
)
def create_call(
    data: ServiceCallCreate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Create a new service call with business logic for recurring detection."""
    from app.services.elevator_service import get_elevator
    if not get_elevator(db, data.elevator_id):
        raise HTTPException(status_code=404, detail="Elevator not found")

    call = service_call_service.create_service_call(db, data, current_user.email)

    # Trigger AI assignment + WhatsApp notification
    try:
        from app.services.ai_assignment_agent import assign_with_confirmation
        from app.services.whatsapp_service import notify_dispatcher_unassigned
        from app.config import get_settings
        assignment = assign_with_confirmation(db, call)
        if not assignment:
            s = get_settings()
            if s.dispatcher_whatsapp:
                elevator = get_elevator(db, data.elevator_id)
                notify_dispatcher_unassigned(
                    s.dispatcher_whatsapp,
                    elevator.address, elevator.city, data.fault_type
                )
    except Exception:
        pass  # Assignment failure must never block call creation

    return call


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="Delete all open service calls",
    description="Deletes every service call that is not yet RESOLVED or CLOSED. Admin only.",
)
def delete_open_calls(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Bulk-delete all open/assigned/in-progress service calls."""
    if current_user.role not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Admin only")
    from app.models.service_call import ServiceCall
    open_statuses = ["OPEN", "ASSIGNED", "IN_PROGRESS"]
    deleted = (
        db.query(ServiceCall)
        .filter(ServiceCall.status.in_(open_statuses))
        .all()
    )
    count = len(deleted)
    for call in deleted:
        db.delete(call)
    db.commit()
    return {"deleted": count}


@router.get(
    "/{call_id}",
    response_model=ServiceCallResponse,
    summary="Get service call",
    description="Return full details of a single service call.",
)
def get_call(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Fetch a single service call by ID."""
    call = service_call_service.get_service_call(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")
    return call


@router.patch(
    "/{call_id}",
    response_model=ServiceCallResponse,
    summary="Update service call",
    description="Update status, priority, or resolution notes. Technicians can only update their own assigned calls.",
)
def update_call(
    call_id: uuid.UUID,
    data: ServiceCallUpdate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Update a service call — enforces technician ownership."""
    call = service_call_service.get_service_call(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")

    # Technicians can only modify calls assigned to them
    if current_user.role == "TECHNICIAN":
        from app.models.assignment import Assignment
        assigned = (
            db.query(Assignment)
            .filter(
                Assignment.service_call_id == call_id,
                Assignment.technician_id == current_user.id,
            )
            .first()
        )
        if not assigned:
            raise HTTPException(status_code=403, detail="You can only update your own assigned calls")

    updated = service_call_service.update_service_call(db, call_id, data, current_user.email)

    # Cancel any PENDING_CONFIRMATION assignments when call details are edited
    from app.models.assignment import Assignment
    from app.services.whatsapp_service import _send_message

    pending = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status == "PENDING_CONFIRMATION"
    ).all()
    for a in pending:
        a.status = "CANCELLED"
        tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
        if tech:
            tech_phone = tech.whatsapp_number or tech.phone
            _send_message(tech_phone, f"ℹ️ הקריאה שנשלחה אליך עודכנה ובוטלה. ייתכן שתישלח שוב בקרוב.")
    if pending:
        db.commit()

    return updated


@router.get(
    "/{call_id}/audit",
    response_model=List[AuditLogResponse],
    summary="Audit log",
    description="Return the full status-change audit trail for a service call.",
)
def get_audit_log(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return the audit trail for a service call."""
    from app.models.assignment import AuditLog
    return db.query(AuditLog).filter(AuditLog.service_call_id == call_id).order_by(AuditLog.changed_at).all()


@router.get(
    "/{call_id}/details",
    response_model=CallDetailResponse,
    summary="Call details",
    description="Return enriched call details including elevator info, technician assignments, and audit log.",
)
def get_call_details(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return enriched call details for the dashboard detail modal."""
    from app.models.assignment import Assignment, AuditLog
    from app.models.elevator import Elevator

    call = service_call_service.get_service_call(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")

    elevator = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    assignments_raw = (
        db.query(Assignment)
        .filter(Assignment.service_call_id == call_id)
        .order_by(Assignment.assigned_at.desc())
        .all()
    )
    audit_raw = (
        db.query(AuditLog)
        .filter(AuditLog.service_call_id == call_id)
        .order_by(AuditLog.changed_at)
        .all()
    )

    assignment_details = []
    for a in assignments_raw:
        tech = db.query(Technician).filter(Technician.id == a.technician_id).first()
        assignment_details.append(AssignmentDetailResponse(
            id=a.id,
            technician_id=a.technician_id,
            technician_name=tech.name if tech else "—",
            assignment_type=a.assignment_type,
            status=a.status,
            travel_minutes=a.travel_minutes,
            assigned_at=a.assigned_at,
        ))

    return CallDetailResponse(
        id=call.id,
        elevator_id=call.elevator_id,
        reported_by=call.reported_by,
        description=call.description,
        priority=call.priority,
        status=call.status,
        fault_type=call.fault_type,
        is_recurring=call.is_recurring,
        resolution_notes=call.resolution_notes,
        quote_needed=call.quote_needed,
        created_at=call.created_at,
        assigned_at=call.assigned_at,
        resolved_at=call.resolved_at,
        elevator_address=elevator.address if elevator else "—",
        elevator_city=elevator.city if elevator else "—",
        elevator_serial=elevator.serial_number if elevator else None,
        assignments=assignment_details,
        audit_logs=audit_raw,
    )
