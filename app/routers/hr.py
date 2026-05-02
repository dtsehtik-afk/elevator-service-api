"""HR router — ניהול משאבי אנוש (Human Resources)."""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.hr_record import HRRecord
from app.models.technician import Technician

router = APIRouter(prefix="/hr", tags=["HR"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class HRRecordUpsert(BaseModel):
    employment_start: Optional[date] = None
    employment_end: Optional[date] = None
    employment_type: Optional[str] = "FULL_TIME"
    salary_type: Optional[str] = "MONTHLY"
    base_salary: Optional[float] = None
    hourly_rate: Optional[float] = None
    id_number: Optional[str] = None
    bank_account: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    notes: Optional[str] = None


class TechnicianHRProfile(BaseModel):
    # Technician fields
    technician_id: str
    name: str
    email: str
    phone: Optional[str]
    role: str
    is_available: bool
    is_active: bool
    # HR record fields (nullable if no record yet)
    hr_id: Optional[str] = None
    employment_start: Optional[date] = None
    employment_end: Optional[date] = None
    employment_type: Optional[str] = None
    salary_type: Optional[str] = None
    base_salary: Optional[float] = None
    hourly_rate: Optional[float] = None
    id_number: Optional[str] = None
    bank_account: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


def _build_profile(tech: Technician) -> TechnicianHRProfile:
    hr = tech.hr_record
    return TechnicianHRProfile(
        technician_id=str(tech.id),
        name=tech.name,
        email=tech.email,
        phone=tech.phone,
        role=tech.role,
        is_available=tech.is_available,
        is_active=tech.is_active,
        hr_id=str(hr.id) if hr else None,
        employment_start=hr.employment_start if hr else None,
        employment_end=hr.employment_end if hr else None,
        employment_type=hr.employment_type if hr else None,
        salary_type=hr.salary_type if hr else None,
        base_salary=hr.base_salary if hr else None,
        hourly_rate=hr.hourly_rate if hr else None,
        id_number=hr.id_number if hr else None,
        bank_account=hr.bank_account if hr else None,
        emergency_contact=hr.emergency_contact if hr else None,
        emergency_phone=hr.emergency_phone if hr else None,
        notes=hr.notes if hr else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats")
def hr_stats(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
) -> Dict[str, Any]:
    """Summary statistics: total staff, employment type breakdown, avg salary."""
    techs = db.query(Technician).filter(Technician.is_active == True).all()  # noqa: E712
    total = len(techs)
    available = sum(1 for t in techs if t.is_available)

    by_type: Dict[str, int] = {}
    salaries: list[float] = []
    for t in techs:
        hr = t.hr_record
        if hr:
            etype = hr.employment_type or "FULL_TIME"
            by_type[etype] = by_type.get(etype, 0) + 1
            if hr.base_salary:
                salaries.append(hr.base_salary)

    avg_salary = round(sum(salaries) / len(salaries), 2) if salaries else None

    by_role: Dict[str, int] = {}
    for t in techs:
        by_role[t.role] = by_role.get(t.role, 0) + 1

    return {
        "total_staff": total,
        "available": available,
        "by_employment_type": by_type,
        "by_role": by_role,
        "avg_salary": avg_salary,
    }


@router.get("", response_model=List[TechnicianHRProfile])
def list_hr(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List all technicians with their HR record (merged)."""
    techs = db.query(Technician).order_by(Technician.name).all()
    return [_build_profile(t) for t in techs]


@router.get("/{technician_id}", response_model=TechnicianHRProfile)
def get_hr(
    technician_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Get one technician's full HR profile."""
    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    return _build_profile(tech)


@router.put("/{technician_id}", response_model=TechnicianHRProfile)
def upsert_hr(
    technician_id: uuid.UUID,
    data: HRRecordUpsert,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """Create or update the HR record for a technician (admin only)."""
    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    hr = db.query(HRRecord).filter(HRRecord.technician_id == technician_id).first()
    if hr is None:
        hr = HRRecord(technician_id=technician_id)
        db.add(hr)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(hr, field, value)

    db.commit()
    db.refresh(tech)
    return _build_profile(tech)
