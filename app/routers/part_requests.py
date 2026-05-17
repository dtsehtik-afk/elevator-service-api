"""Part request router — approval workflow for technician part replacement."""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician
from app.schemas.part_request import (
    PartRequestCreate, PartRequestApprove, PartRequestReject, PartRequestResponse,
)
from app.services import part_request_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _enrich(pr) -> PartRequestResponse:
    r = PartRequestResponse.model_validate(pr)
    r.part_name = pr.part.name if pr.part else None
    r.part_sku = pr.part.sku if pr.part else None
    r.requester_name = pr.requester.name if pr.requester else None
    r.approver_name = pr.approver.name if pr.approver else None
    r.source_warehouse_name = pr.source_warehouse.name if pr.source_warehouse else None
    return r


@router.post("", response_model=PartRequestResponse, status_code=201)
def create_part_request(
    data: PartRequestCreate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    pr = part_request_service.create_request(db, data, current_user)
    return _enrich(pr)


@router.get("", response_model=List[PartRequestResponse])
def list_part_requests(
    service_call_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    items = part_request_service.list_requests(db, service_call_id=service_call_id, status=status)
    return [_enrich(pr) for pr in items]


@router.get("/pending-count", response_model=dict)
def pending_count(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "MANAGER", "DISPATCHER"):
        return {"count": 0}
    count = part_request_service.pending_count(db)
    return {"count": count}


@router.post("/{pr_id}/approve", response_model=PartRequestResponse)
def approve_part_request(
    pr_id: UUID,
    data: PartRequestApprove,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "MANAGER", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Manager only")
    pr = part_request_service.approve_request(db, pr_id, current_user, data.approval_notes)
    return _enrich(pr)


@router.post("/{pr_id}/reject", response_model=PartRequestResponse)
def reject_part_request(
    pr_id: UUID,
    data: PartRequestReject,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "MANAGER", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Manager only")
    pr = part_request_service.reject_request(db, pr_id, current_user, data.rejection_reason)
    return _enrich(pr)


@router.post("/{pr_id}/issue", response_model=PartRequestResponse)
def issue_part(
    pr_id: UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Actually deduct from warehouse stock. Only allowed after approval."""
    pr = part_request_service.issue_part(db, pr_id, current_user)
    return _enrich(pr)


@router.post("/{pr_id}/return-faulty", response_model=PartRequestResponse)
def return_faulty_part(
    pr_id: UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Mark the faulty part as returned to main warehouse."""
    pr = part_request_service.mark_faulty_returned(db, pr_id)
    return _enrich(pr)
