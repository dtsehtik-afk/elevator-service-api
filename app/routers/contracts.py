"""Contracts router — חוזים."""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.contract import Contract, ElevatorContract
from app.models.customer import Customer
from app.models.elevator import Elevator
from app.models.technician import Technician
from app.schemas.contract import ContractCreate, ContractResponse, ContractUpdate

router = APIRouter(prefix="/contracts", tags=["Contracts"])


def _next_number(db: Session) -> str:
    year = date.today().year
    count = db.query(func.count(Contract.id)).filter(
        func.extract("year", Contract.created_at) == year
    ).scalar() or 0
    return f"C-{year}-{count + 1:04d}"


def _enrich(c: Contract, db: Session) -> ContractResponse:
    r = ContractResponse.model_validate(c)
    r.customer_name = c.customer.name if c.customer else None
    r.elevator_count = db.query(ElevatorContract).filter(ElevatorContract.contract_id == c.id).count()
    return r


@router.get("", response_model=List[ContractResponse])
def list_contracts(
    customer_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Contract)
    if customer_id:
        q = q.filter(Contract.customer_id == customer_id)
    if status:
        q = q.filter(Contract.status == status)
    if contract_type:
        q = q.filter(Contract.contract_type == contract_type)
    contracts = q.order_by(Contract.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich(c, db) for c in contracts]


@router.post("", response_model=ContractResponse, status_code=201)
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    elevator_ids = data.elevator_ids
    payload = data.model_dump(exclude={"elevator_ids"})
    payload["number"] = _next_number(db)

    contract = Contract(**payload)
    db.add(contract)
    db.flush()

    for eid in elevator_ids:
        elev = db.query(Elevator).filter(Elevator.id == eid).first()
        if elev:
            db.add(ElevatorContract(elevator_id=eid, contract_id=contract.id))

    db.commit()
    db.refresh(contract)
    return _enrich(contract, db)


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _enrich(c, db)


@router.patch("/{contract_id}", response_model=ContractResponse)
def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")

    update_data = data.model_dump(exclude_unset=True)
    elevator_ids = update_data.pop("elevator_ids", None)

    for k, v in update_data.items():
        setattr(c, k, v)

    if elevator_ids is not None:
        db.query(ElevatorContract).filter(ElevatorContract.contract_id == contract_id).delete()
        for eid in elevator_ids:
            db.add(ElevatorContract(elevator_id=eid, contract_id=contract_id))

    db.commit()
    db.refresh(c)
    return _enrich(c, db)


@router.delete("/{contract_id}", status_code=204)
def delete_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    db.delete(c)
    db.commit()


@router.get("/{contract_id}/elevators")
def get_contract_elevators(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    links = db.query(ElevatorContract).filter(ElevatorContract.contract_id == contract_id).all()
    result = []
    for link in links:
        e = link.elevator
        result.append({"id": str(e.id), "address": e.address, "city": e.city, "status": e.status})
    return result
