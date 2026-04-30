"""Leads router — CRM לידים."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.lead import Lead
from app.models.technician import Technician
from app.schemas.lead import LeadCreate, LeadResponse, LeadUpdate

router = APIRouter(prefix="/leads", tags=["Leads"])


def _enrich(lead: Lead) -> LeadResponse:
    r = LeadResponse.model_validate(lead)
    r.customer_name = lead.customer.name if lead.customer else None
    return r


@router.get("", response_model=List[LeadResponse])
def list_leads(
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Lead)
    if status:
        q = q.filter(Lead.status == status)
    if owner:
        q = q.filter(Lead.owner.ilike(f"%{owner}%"))
    if source:
        q = q.filter(Lead.source == source)
    leads = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich(l) for l in leads]


@router.post("", response_model=LeadResponse, status_code=201)
def create_lead(
    data: LeadCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    lead = Lead(**data.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _enrich(lead)


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _enrich(lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: uuid.UUID,
    data: LeadUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(lead, k, v)
    db.commit()
    db.refresh(lead)
    return _enrich(lead)


@router.delete("/{lead_id}", status_code=204)
def delete_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()


@router.post("/{lead_id}/convert", response_model=dict)
def convert_lead_to_customer(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Mark lead as WON and link to a new customer."""
    from app.models.customer import Customer

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    customer = Customer(
        name=lead.company or lead.name,
        phone=lead.phone,
        email=lead.email,
        customer_type="CORPORATE" if lead.company else "PRIVATE",
    )
    db.add(customer)
    db.flush()

    lead.customer_id = customer.id
    lead.status = "WON"
    db.commit()
    return {"customer_id": str(customer.id), "customer_name": customer.name}


@router.get("/board/kanban", tags=["CRM"])
def kanban_board(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Returns leads grouped by status for Kanban view."""
    statuses = ["NEW", "CONTACTED", "QUALIFIED", "PROPOSAL", "WON", "LOST"]
    board = {}
    for s in statuses:
        leads = db.query(Lead).filter(Lead.status == s).order_by(Lead.created_at.desc()).all()
        board[s] = [
            {
                "id": str(l.id),
                "name": l.name,
                "company": l.company,
                "phone": l.phone,
                "estimated_value": float(l.estimated_value) if l.estimated_value else None,
                "owner": l.owner,
                "stage": l.stage,
            }
            for l in leads
        ]
    return board
