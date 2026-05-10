"""Contacts router — manage contacts linked to buildings or management companies."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.contact import Contact
from app.models.technician import Technician
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get("", response_model=List[ContactResponse])
def list_contacts(
    elevator_id: Optional[uuid.UUID] = Query(None),
    building_id: Optional[uuid.UUID] = Query(None),
    management_company_id: Optional[uuid.UUID] = Query(None),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Contact)
    if elevator_id:
        q = q.filter(Contact.elevator_id == elevator_id)
    if building_id:
        q = q.filter(Contact.building_id == building_id)
    if management_company_id:
        q = q.filter(Contact.management_company_id == management_company_id)
    if role:
        q = q.filter(Contact.role == role)
    if search:
        q = q.filter(
            Contact.name.ilike(f"%{search}%") |
            Contact.phone.ilike(f"%{search}%") |
            Contact.email.ilike(f"%{search}%")
        )
    return q.order_by(Contact.name).offset(skip).limit(limit).all()


@router.post("", response_model=ContactResponse, status_code=201)
def create_contact(
    data: ContactCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    contact = Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: uuid.UUID,
    data: ContactUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(contact, k, v)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/admin/purge-orphan-auto-contacts", status_code=200)
def purge_orphan_auto_contacts(
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Delete all auto-added contacts that have no building link (building_id IS NULL).
    These were incorrectly created and pollute every elevator's contact list.
    Admin only.
    """
    from app.models.technician import Technician as TechModel
    if current_user.role not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Admin only")
    deleted = db.query(Contact).filter(
        Contact.auto_added == True,
        Contact.building_id == None,
        Contact.elevator_id == None,
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
