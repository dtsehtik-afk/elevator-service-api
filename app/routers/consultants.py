"""Consultant CRUD endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_dispatcher_or_admin
from app.database import get_db
from app.models.consultant import Consultant
from app.models.elevator import Elevator

router = APIRouter(prefix="/consultants", tags=["Consultants"])


class ConsultantCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True
    consultant_contacts: List[dict] = []


class ConsultantUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    consultant_contacts: Optional[List[dict]] = None


def _serialize(consultant: Consultant, db: Session) -> dict:
    elevator_count = db.query(Elevator).filter(Elevator.consultant_id == consultant.id).count()
    return {
        "id": str(consultant.id),
        "name": consultant.name,
        "phone": consultant.phone,
        "email": consultant.email,
        "address": consultant.address,
        "notes": consultant.notes,
        "is_active": consultant.is_active,
        "consultant_contacts": consultant.consultant_contacts or [],
        "elevator_count": elevator_count,
        "created_at": consultant.created_at.isoformat() if consultant.created_at else None,
    }


@router.get("", summary="List consultants")
def list_consultants(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    active_only: bool = Query(False),
):
    q = db.query(Consultant)
    if active_only:
        q = q.filter(Consultant.is_active == True)
    consultants = q.order_by(Consultant.name).all()
    return [_serialize(c, db) for c in consultants]


@router.post("", summary="Create consultant")
def create_consultant(
    data: ConsultantCreate,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    existing = db.query(Consultant).filter(Consultant.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="יועץ עם שם זה כבר קיים")
    consultant = Consultant(**data.model_dump())
    db.add(consultant)
    db.commit()
    db.refresh(consultant)
    return _serialize(consultant, db)


@router.get("/{consultant_id}", summary="Get consultant with its elevators")
def get_consultant(
    consultant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    consultant = db.query(Consultant).filter(Consultant.id == consultant_id).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="היועץ לא נמצא")
    elevators = db.query(Elevator).filter(Elevator.consultant_id == consultant_id).all()
    result = _serialize(consultant, db)
    result["elevators"] = [
        {"id": str(e.id), "address": e.address, "city": e.city,
         "building_name": e.building_name, "status": e.status}
        for e in elevators
    ]
    return result


@router.patch("/{consultant_id}", summary="Update consultant")
def update_consultant(
    consultant_id: uuid.UUID,
    data: ConsultantUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    consultant = db.query(Consultant).filter(Consultant.id == consultant_id).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="היועץ לא נמצא")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(consultant, field, value)
    db.commit()
    db.refresh(consultant)
    return _serialize(consultant, db)


@router.delete("/{consultant_id}", summary="Delete consultant")
def delete_consultant(
    consultant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    consultant = db.query(Consultant).filter(Consultant.id == consultant_id).first()
    if not consultant:
        raise HTTPException(status_code=404, detail="היועץ לא נמצא")
    db.query(Elevator).filter(Elevator.consultant_id == consultant_id).update(
        {Elevator.consultant_id: None}
    )
    db.delete(consultant)
    db.commit()
    return {"ok": True}
