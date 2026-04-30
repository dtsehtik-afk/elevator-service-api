"""Customers router — CRM לקוחות עם היררכיית לקוח אב."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.building import Building
from app.models.elevator import Elevator
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.technician import Technician
from app.schemas.customer import CustomerCreate, CustomerDetail, CustomerResponse, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["Customers"])


def _enrich(c: Customer, db: Session) -> CustomerResponse:
    r = CustomerResponse.model_validate(c)
    r.parent_name = c.parent.name if c.parent else None
    r.children_count = len(c.children)
    r.elevator_count = db.query(Elevator).filter(Elevator.customer_id == c.id).count()
    r.active_contracts = db.query(Contract).filter(
        Contract.customer_id == c.id, Contract.status == "ACTIVE"
    ).count()
    r.open_invoices = db.query(Invoice).filter(
        Invoice.customer_id == c.id, Invoice.status.in_(["SENT", "OVERDUE", "PARTIAL"])
    ).count()
    return r


@router.get("", response_model=List[CustomerResponse])
def list_customers(
    search: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    parent_only: bool = Query(False, description="Return only top-level customers (no parent)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Customer)
    if search:
        q = q.filter(Customer.name.ilike(f"%{search}%"))
    if customer_type:
        q = q.filter(Customer.customer_type == customer_type)
    if city:
        q = q.filter(Customer.city.ilike(f"%{city}%"))
    if is_active is not None:
        q = q.filter(Customer.is_active == is_active)
    if parent_only:
        q = q.filter(Customer.parent_id.is_(None))
    customers = q.order_by(Customer.name).offset(skip).limit(limit).all()
    return [_enrich(c, db) for c in customers]


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = Customer(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _enrich(c, db)


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    r = CustomerDetail.model_validate(c)
    r.parent_name = c.parent.name if c.parent else None
    r.children_count = len(c.children)
    r.children = c.children
    r.elevator_count = db.query(Elevator).filter(Elevator.customer_id == c.id).count()
    r.active_contracts = db.query(Contract).filter(
        Contract.customer_id == c.id, Contract.status == "ACTIVE"
    ).count()
    r.open_invoices = db.query(Invoice).filter(
        Invoice.customer_id == c.id, Invoice.status.in_(["SENT", "OVERDUE", "PARTIAL"])
    ).count()
    return r


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return _enrich(c, db)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    # detach related before delete
    db.query(Building).filter(Building.customer_id == customer_id).update({Building.customer_id: None})
    db.query(Elevator).filter(Elevator.customer_id == customer_id).update({Elevator.customer_id: None})
    db.delete(c)
    db.commit()


@router.get("/{customer_id}/related", tags=["Cross-Reference"])
def get_customer_related(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Cross-reference panel: everything linked to this customer."""
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    elevators = db.query(Elevator).filter(Elevator.customer_id == customer_id).all()
    buildings = db.query(Building).filter(Building.customer_id == customer_id).all()
    contracts = db.query(Contract).filter(Contract.customer_id == customer_id).all()
    invoices = db.query(Invoice).filter(Invoice.customer_id == customer_id).all()

    return {
        "parent": {"id": str(c.parent_id), "name": c.parent.name} if c.parent else None,
        "children": [{"id": str(ch.id), "name": ch.name, "type": ch.customer_type} for ch in c.children],
        "elevators": [{"id": str(e.id), "address": e.address, "city": e.city, "status": e.status} for e in elevators],
        "buildings": [{"id": str(b.id), "address": b.address, "city": b.city} for b in buildings],
        "contracts": [{"id": str(ct.id), "number": ct.number, "type": ct.contract_type, "status": ct.status} for ct in contracts],
        "invoices": [{"id": str(inv.id), "number": inv.number, "total": float(inv.total), "status": inv.status} for inv in invoices],
    }
