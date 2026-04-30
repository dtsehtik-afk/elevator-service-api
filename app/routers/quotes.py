"""Quotes router — הצעות מחיר."""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.elevator import Elevator
from app.models.quote import Quote
from app.models.technician import Technician
from app.schemas.quote import QuoteCreate, QuoteResponse, QuoteUpdate

router = APIRouter(prefix="/quotes", tags=["Quotes"])


def _next_number(db: Session) -> str:
    year = date.today().year
    count = db.query(func.count(Quote.id)).filter(
        func.extract("year", Quote.created_at) == year
    ).scalar() or 0
    return f"Q-{year}-{count + 1:04d}"


def _enrich(q: Quote) -> QuoteResponse:
    r = QuoteResponse.model_validate(q)
    r.customer_name = q.customer.name if q.customer else None
    if q.elevator:
        r.elevator_address = f"{q.elevator.address}, {q.elevator.city}"
    return r


@router.get("", response_model=List[QuoteResponse])
def list_quotes(
    customer_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Quote)
    if customer_id:
        q = q.filter(Quote.customer_id == customer_id)
    if status:
        q = q.filter(Quote.status == status)
    quotes = q.order_by(Quote.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich(qt) for qt in quotes]


@router.post("", response_model=QuoteResponse, status_code=201)
def create_quote(
    data: QuoteCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    payload = data.model_dump()
    payload["number"] = _next_number(db)
    q = Quote(**payload)
    db.add(q)
    db.commit()
    db.refresh(q)
    return _enrich(q)


@router.get("/{quote_id}", response_model=QuoteResponse)
def get_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Quote).filter(Quote.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _enrich(q)


@router.patch("/{quote_id}", response_model=QuoteResponse)
def update_quote(
    quote_id: uuid.UUID,
    data: QuoteUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Quote).filter(Quote.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(q, k, v)
    db.commit()
    db.refresh(q)
    return _enrich(q)


@router.delete("/{quote_id}", status_code=204)
def delete_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Quote).filter(Quote.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    db.delete(q)
    db.commit()


@router.post("/{quote_id}/convert-to-contract", response_model=dict)
def convert_to_contract(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Convert an accepted quote into a contract."""
    from app.models.contract import Contract
    from app.schemas.contract import ContractCreate

    q = db.query(Quote).filter(Quote.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    if q.status not in ("ACCEPTED", "SENT"):
        raise HTTPException(status_code=400, detail="Quote must be ACCEPTED or SENT to convert")

    year = date.today().year
    from sqlalchemy import func as _func
    count = db.query(_func.count(Contract.id)).filter(
        _func.extract("year", Contract.created_at) == year
    ).scalar() or 0
    number = f"C-{year}-{count + 1:04d}"

    contract = Contract(
        number=number,
        customer_id=q.customer_id,
        total_value=float(q.total),
        status="PENDING",
        contract_type="SERVICE",
    )
    db.add(contract)
    db.flush()

    q.contract_id = contract.id
    q.status = "ACCEPTED"
    db.commit()
    db.refresh(contract)
    return {"contract_id": str(contract.id), "contract_number": contract.number}
