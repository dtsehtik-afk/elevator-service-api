"""Router for service call CRUD endpoints."""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
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
    limit: int = Query(50, ge=1, le=500),
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
    except Exception as exc:
        logger.error("AI assignment failed for call %s: %s", call.id, exc, exc_info=True)

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


@router.patch(
    "/{call_id}/elevator",
    summary="Reassign service call to a different elevator",
)
def reassign_call_elevator(
    call_id: uuid.UUID,
    elevator_id: uuid.UUID = Query(..., description="New elevator UUID"),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Change the elevator linked to an open service call (admin/dispatcher only)."""
    if current_user.role == "TECHNICIAN":
        raise HTTPException(status_code=403, detail="Technicians cannot reassign call elevators")

    call = service_call_service.get_service_call(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")
    if call.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Cannot reassign a resolved call")

    from app.models.elevator import Elevator
    new_elev = db.query(Elevator).filter(Elevator.id == elevator_id).first()
    if not new_elev:
        raise HTTPException(status_code=404, detail="Elevator not found")

    old_elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
    old_addr = f"{old_elev.address}, {old_elev.city}" if old_elev else "לא ידוע"
    new_addr = f"{new_elev.address}, {new_elev.city}"

    call.elevator_id = elevator_id

    from app.models.assignment import AuditLog
    db.add(AuditLog(
        service_call_id=call.id,
        changed_by=current_user.email,
        old_status=call.status,
        new_status=call.status,
        notes=f"מעלית שויכה מחדש: {old_addr} → {new_addr}",
    ))
    db.commit()
    db.refresh(call)

    # Notify assigned technician of address change
    from app.models.assignment import Assignment
    from app.models.technician import Technician as TechModel
    active = db.query(Assignment).filter(
        Assignment.service_call_id == call.id,
        Assignment.status.in_(["CONFIRMED", "PENDING_CONFIRMATION"]),
    ).first()
    if active:
        tech = db.query(TechModel).filter(TechModel.id == active.technician_id).first()
        if tech:
            from app.services.whatsapp_service import _send_message
            _send_message(
                tech.whatsapp_number or tech.phone,
                f"⚠️ *עדכון כתובת לקריאה שלך*\n"
                f"מ: {old_addr}\nל: *{new_addr}*",
            )

    return {"ok": True, "new_address": new_addr}


@router.post(
    "/{call_id}/monitor",
    response_model=ServiceCallResponse,
    summary="Set call to MONITORING status",
)
def set_monitoring(
    call_id: uuid.UUID,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Move a call to MONITORING — priority drops to LOW, auto-closes after 7 days."""
    from datetime import datetime, timezone
    from app.models.assignment import Assignment, AuditLog
    from app.models.service_call import ServiceCall

    call = db.query(ServiceCall).filter(ServiceCall.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")
    if call.status in ("CLOSED", "RESOLVED"):
        raise HTTPException(status_code=400, detail="Call already closed")

    old_status = call.status
    old_priority = call.priority
    call.status = "MONITORING"
    call.priority = "LOW"
    call.monitoring_notes = notes
    call.monitoring_since = datetime.now(timezone.utc)

    db.add(AuditLog(
        service_call_id=call.id,
        changed_by=current_user.email or current_user.name,
        old_status=old_status,
        new_status="MONITORING",
        notes=f"במעקב (עדיפות שונתה מ-{old_priority} ל-LOW): {notes}" if notes else f"במעקב (עדיפות שונתה מ-{old_priority} ל-LOW)",
    ))

    # Cancel any pending assignments
    pending = db.query(Assignment).filter(
        Assignment.service_call_id == call_id,
        Assignment.status == "PENDING_CONFIRMATION",
    ).all()
    for a in pending:
        a.status = "CANCELLED"

    db.commit()
    db.refresh(call)
    return call


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

    tech_ids = [a.technician_id for a in assignments_raw]
    techs_by_id = {
        t.id: t
        for t in db.query(Technician).filter(Technician.id.in_(tech_ids)).all()
    } if tech_ids else {}

    assignment_details = []
    for a in assignments_raw:
        tech = techs_by_id.get(a.technician_id)
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
