"""Part request service — business logic for technician part replacement approval workflow."""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.part_request import PartRequest
from app.models.part import Part
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.models.warehouse import Warehouse
from app.schemas.part_request import PartRequestCreate
from app.services.activity_service import log_activity

logger = logging.getLogger(__name__)


def _get_service_type_for_call(db: Session, service_call: ServiceCall) -> str:
    """
    Determine service type for the elevator on this call.
    Returns 'COMPREHENSIVE' or 'REGULAR'.
    """
    from app.models.elevator import Elevator
    from app.models.contract import Contract

    elev = db.query(Elevator).filter(Elevator.id == service_call.elevator_id).first()
    if not elev:
        return "REGULAR"

    # Check elevator's service_type field first
    if elev.service_type == "COMPREHENSIVE":
        return "COMPREHENSIVE"

    # Also check active contracts for this customer
    if elev.customer_id:
        active = db.query(Contract).filter(
            Contract.customer_id == elev.customer_id,
            Contract.status == "ACTIVE",
            Contract.contract_type.in_(["MAINTENANCE", "SERVICE"]),
        ).first()
        if active and active.contract_type == "MAINTENANCE":
            return "COMPREHENSIVE"

    return "REGULAR"


def _get_main_warehouse(db: Session) -> Optional[Warehouse]:
    return db.query(Warehouse).filter(Warehouse.warehouse_type == "MAIN", Warehouse.is_active == True).first()  # noqa: E712


def create_request(db: Session, data: PartRequestCreate, current_user: Technician) -> PartRequest:
    from app.models.warehouse_stock import WarehouseStock

    call = db.query(ServiceCall).filter(ServiceCall.id == data.service_call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Service call not found")

    part = db.query(Part).filter(Part.id == data.part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    # Determine source warehouse
    source_wh_id = data.source_warehouse_id
    if not source_wh_id:
        main_wh = _get_main_warehouse(db)
        if main_wh:
            source_wh_id = main_wh.id

    # Determine service type and approval type
    svc_type = _get_service_type_for_call(db, call)
    if svc_type == "COMPREHENSIVE":
        approval_type = "COMPREHENSIVE_APPROVAL"
    else:
        approval_type = "MANAGER_OVERRIDE"

    # Get main warehouse for faulty part return
    main_wh = _get_main_warehouse(db)

    pr = PartRequest(
        service_call_id=data.service_call_id,
        part_id=data.part_id,
        quantity=data.quantity,
        source_warehouse_id=source_wh_id,
        requested_by=current_user.id,
        notes=data.notes,
        status="PENDING_APPROVAL",
        approval_type=approval_type,
        service_type_snapshot=svc_type,
        return_warehouse_id=main_wh.id if main_wh else None,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    call_ref = f"S{call.call_number:05d}" if call.call_number else str(call.id)[:8]
    log_activity(db, action="part_requested",
                 message=f"{current_user.name} ביקש חלק: {part.name} (כמות: {pr.quantity}) לקריאה {call_ref}",
                 actor_name=current_user.name,
                 entity_type="part_request", entity_id=pr.id, entity_ref=call_ref)
    db.commit()

    # Notify managers via WhatsApp
    _notify_managers_new_request(db, pr, part, call, current_user, svc_type)

    return pr


def _notify_managers_new_request(
    db: Session, pr: PartRequest, part: Part, call: ServiceCall, requester: Technician, svc_type: str
):
    try:
        import os
        from app.services.whatsapp_service import send_whatsapp_message

        dispatcher_numbers = [
            n.strip() for n in os.getenv("DISPATCHER_WHATSAPP", "").split(",") if n.strip()
        ]
        if not dispatcher_numbers:
            return

        elev_addr = ""
        from app.models.elevator import Elevator
        elev = db.query(Elevator).filter(Elevator.id == call.elevator_id).first()
        if elev:
            elev_addr = f"{elev.address}, {elev.city}"

        approval_label = "אישור חריג" if svc_type == "REGULAR" else "אישור מנהל שירות"
        msg = (
            f"🔧 *בקשת חלק חדשה — {approval_label}*\n"
            f"טכנאי: {requester.name}\n"
            f"קריאה: {call.call_number or call.id}\n"
            f"כתובת: {elev_addr}\n"
            f"חלק: {part.name} (כמות: {pr.quantity})\n"
            f"סוג שירות: {'מקיף' if svc_type == 'COMPREHENSIVE' else 'רגיל'}\n\n"
            f"לאישור/דחייה:\n"
            f"🔗 {os.getenv('APP_BASE_URL', 'https://lift-agent.com').rstrip('/')}/part-requests"
        )

        for number in dispatcher_numbers:
            try:
                send_whatsapp_message(number, msg)
            except Exception as e:
                logger.warning("Failed to notify dispatcher %s: %s", number, e)
    except Exception as e:
        logger.warning("Part request notification failed: %s", e)


def list_requests(
    db: Session,
    service_call_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
) -> List[PartRequest]:
    q = db.query(PartRequest)
    if service_call_id:
        q = q.filter(PartRequest.service_call_id == service_call_id)
    if status:
        q = q.filter(PartRequest.status == status)
    return q.order_by(PartRequest.created_at.desc()).all()


def pending_count(db: Session) -> int:
    return db.query(PartRequest).filter(PartRequest.status == "PENDING_APPROVAL").count()


def approve_request(
    db: Session, pr_id: uuid.UUID, approver: Technician, approval_notes: Optional[str]
) -> PartRequest:
    pr = db.query(PartRequest).filter(PartRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Part request not found")
    if pr.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Cannot approve in status: {pr.status}")

    pr.status = "APPROVED"
    pr.approved_by = approver.id
    pr.approved_at = datetime.now(timezone.utc)
    pr.approval_notes = approval_notes
    db.commit()
    db.refresh(pr)

    part = db.query(Part).filter(Part.id == pr.part_id).first()
    call = db.query(ServiceCall).filter(ServiceCall.id == pr.service_call_id).first()
    call_ref = f"S{call.call_number:05d}" if call and call.call_number else str(pr.service_call_id)[:8]
    log_activity(db, action="part_approved",
                 message=f"חלק {part.name if part else ''} אושר ע\"י {approver.name} לקריאה {call_ref}",
                 actor_name=approver.name,
                 entity_type="part_request", entity_id=pr.id, entity_ref=call_ref)
    db.commit()

    _notify_requester(db, pr, approved=True)
    return pr


def reject_request(
    db: Session, pr_id: uuid.UUID, rejector: Technician, reason: str
) -> PartRequest:
    pr = db.query(PartRequest).filter(PartRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Part request not found")
    if pr.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Cannot reject in status: {pr.status}")

    pr.status = "REJECTED"
    pr.approved_by = rejector.id
    pr.rejection_reason = reason
    db.commit()
    db.refresh(pr)

    part = db.query(Part).filter(Part.id == pr.part_id).first()
    call = db.query(ServiceCall).filter(ServiceCall.id == pr.service_call_id).first()
    call_ref = f"S{call.call_number:05d}" if call and call.call_number else str(pr.service_call_id)[:8]
    log_activity(db, action="part_rejected",
                 message=f"בקשת חלק {part.name if part else ''} נדחתה ע\"י {rejector.name} — {reason}",
                 actor_name=rejector.name,
                 entity_type="part_request", entity_id=pr.id, entity_ref=call_ref)
    db.commit()

    _notify_requester(db, pr, approved=False)
    return pr


def _notify_requester(db: Session, pr: PartRequest, approved: bool):
    try:
        from app.services.whatsapp_service import send_whatsapp_message

        tech = db.query(Technician).filter(Technician.id == pr.requested_by).first()
        if not tech or not tech.whatsapp_number:
            return

        part = db.query(Part).filter(Part.id == pr.part_id).first()
        part_name = part.name if part else str(pr.part_id)

        call = db.query(ServiceCall).filter(ServiceCall.id == pr.service_call_id).first()
        call_ref = call.call_number or str(pr.service_call_id) if call else str(pr.service_call_id)

        if approved:
            msg = (
                f"✅ *בקשת חלק אושרה*\n"
                f"חלק: {part_name} (כמות: {pr.quantity})\n"
                f"קריאה: {call_ref}\n"
                f"{pr.approval_notes or ''}\n"
                f"ניתן למשוך את החלק מהמחסן."
            )
        else:
            msg = (
                f"❌ *בקשת חלק נדחתה*\n"
                f"חלק: {part_name} (כמות: {pr.quantity})\n"
                f"קריאה: {call_ref}\n"
                f"סיבה: {pr.rejection_reason}"
            )
        send_whatsapp_message(tech.whatsapp_number, msg)
    except Exception as e:
        logger.warning("Failed to notify requester about part request: %s", e)


def issue_part(db: Session, pr_id: uuid.UUID, current_user: Technician) -> PartRequest:
    """Deduct stock from source warehouse. Must be APPROVED first."""
    from app.models.warehouse_stock import WarehouseStock

    pr = db.query(PartRequest).filter(PartRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Part request not found")
    if pr.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Part request must be approved before issuing")

    # Check stock
    stock = db.query(WarehouseStock).filter(
        WarehouseStock.part_id == pr.part_id,
        WarehouseStock.warehouse_id == pr.source_warehouse_id,
    ).first()
    available = stock.quantity if stock else 0
    if available < pr.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock: {available} available, {pr.quantity} requested"
        )

    # Deduct from source warehouse
    stock.quantity -= pr.quantity

    # Update global part quantity
    part = db.query(Part).filter(Part.id == pr.part_id).first()
    if part:
        part.quantity = max(0, part.quantity - pr.quantity)

    pr.status = "ISSUED"
    db.commit()
    db.refresh(pr)

    call = db.query(ServiceCall).filter(ServiceCall.id == pr.service_call_id).first()
    call_ref = f"S{call.call_number:05d}" if call and call.call_number else str(pr.service_call_id)[:8]
    log_activity(db, action="part_issued",
                 message=f"חלק {part.name} הוצא מהמחסן (כמות: {pr.quantity}) לקריאה {call_ref}",
                 actor_name=current_user.name if current_user else None,
                 entity_type="part_request", entity_id=pr.id, entity_ref=call_ref)
    db.commit()
    return pr


def mark_faulty_returned(db: Session, pr_id: uuid.UUID) -> PartRequest:
    pr = db.query(PartRequest).filter(PartRequest.id == pr_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Part request not found")
    pr.faulty_part_returned = True
    db.commit()
    db.refresh(pr)
    return pr


def call_has_pending_returns(db: Session, service_call_id: uuid.UUID) -> bool:
    """Returns True if there are ISSUED part requests where faulty part has not been returned."""
    return db.query(PartRequest).filter(
        PartRequest.service_call_id == service_call_id,
        PartRequest.status == "ISSUED",
        PartRequest.faulty_part_returned == False,  # noqa: E712
    ).count() > 0
