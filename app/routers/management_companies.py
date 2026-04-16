"""Management company CRUD endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_dispatcher_or_admin
from app.database import get_db
from app.models.management_company import ManagementCompany
from app.models.elevator import Elevator

router = APIRouter(prefix="/management-companies", tags=["Management Companies"])


class CompanyCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    caller_phones: List[str] = []
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    caller_phones: Optional[List[str]] = None
    notes: Optional[str] = None


def _serialize(company: ManagementCompany, db: Session) -> dict:
    elevator_count = db.query(Elevator).filter(Elevator.management_company_id == company.id).count()
    return {
        "id": str(company.id),
        "name": company.name,
        "contact_name": company.contact_name,
        "phone": company.phone,
        "email": company.email,
        "caller_phones": company.caller_phones or [],
        "notes": company.notes,
        "elevator_count": elevator_count,
        "created_at": company.created_at.isoformat() if company.created_at else None,
    }


@router.get("", summary="List management companies")
def list_companies(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    companies = db.query(ManagementCompany).order_by(ManagementCompany.name).all()
    return [_serialize(c, db) for c in companies]


@router.post("", summary="Create management company")
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    existing = db.query(ManagementCompany).filter(ManagementCompany.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="חברת ניהול עם שם זה כבר קיימת")
    company = ManagementCompany(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return _serialize(company, db)


@router.get("/{company_id}", summary="Get management company with its elevators")
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    company = db.query(ManagementCompany).filter(ManagementCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="חברת הניהול לא נמצאה")
    elevators = db.query(Elevator).filter(Elevator.management_company_id == company_id).all()
    result = _serialize(company, db)
    result["elevators"] = [
        {"id": str(e.id), "address": e.address, "city": e.city,
         "building_name": e.building_name, "status": e.status}
        for e in elevators
    ]
    return result


@router.patch("/{company_id}", summary="Update management company")
def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    company = db.query(ManagementCompany).filter(ManagementCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="חברת הניהול לא נמצאה")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return _serialize(company, db)


@router.delete("/{company_id}", summary="Delete management company")
def delete_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    company = db.query(ManagementCompany).filter(ManagementCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="חברת הניהול לא נמצאה")
    # Detach elevators before deletion (FK is SET NULL)
    db.query(Elevator).filter(Elevator.management_company_id == company_id).update(
        {Elevator.management_company_id: None}
    )
    db.delete(company)
    db.commit()
    return {"ok": True}


@router.post("/{company_id}/assign-elevator", summary="Assign an elevator to this company")
def assign_elevator(
    company_id: uuid.UUID,
    elevator_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    company = db.query(ManagementCompany).filter(ManagementCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="חברת הניהול לא נמצאה")
    elevator = db.query(Elevator).filter(Elevator.id == elevator_id).first()
    if not elevator:
        raise HTTPException(status_code=404, detail="המעלית לא נמצאה")
    elevator.management_company_id = company_id
    db.commit()
    return {"ok": True, "elevator_address": f"{elevator.address}, {elevator.city}"}


@router.post("/{company_id}/remove-elevator", summary="Remove an elevator from this company")
def remove_elevator(
    company_id: uuid.UUID,
    elevator_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    elevator = db.query(Elevator).filter(
        Elevator.id == elevator_id,
        Elevator.management_company_id == company_id,
    ).first()
    if not elevator:
        raise HTTPException(status_code=404, detail="המעלית לא נמצאה תחת חברה זו")
    elevator.management_company_id = None
    db.commit()
    return {"ok": True}
