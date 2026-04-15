"""Business logic for technician management."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.assignment import Assignment
from app.models.service_call import ServiceCall
from app.models.technician import Technician
from app.schemas.technician import TechnicianCreate, TechnicianStats, TechnicianUpdate


def create_technician(db: Session, data: TechnicianCreate) -> Technician:
    """Create a new technician account with bcrypt-hashed password.

    Args:
        db: Database session.
        data: Validated technician creation data.

    Returns:
        Created Technician ORM object.

    Raises:
        ValueError: If a technician with the same email already exists.
    """
    existing = db.query(Technician).filter(Technician.email == data.email).first()
    if existing:
        raise ValueError("Email already registered")

    tech = Technician(
        name=data.name,
        email=data.email,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role=data.role,
        specializations=data.specializations,
        area_codes=data.area_codes,
        max_daily_calls=data.max_daily_calls,
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)
    return tech


def get_technician(db: Session, technician_id: uuid.UUID) -> Optional[Technician]:
    """Fetch a single technician by UUID."""
    return db.query(Technician).filter(Technician.id == technician_id).first()


def list_technicians(
    db: Session,
    is_available: Optional[bool] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Technician]:
    """Return a filtered list of technicians."""
    query = db.query(Technician)
    if is_available is not None:
        query = query.filter(Technician.is_available == is_available)
    if is_active is not None:
        query = query.filter(Technician.is_active == is_active)
    return query.offset(skip).limit(min(limit, 100)).all()


def update_technician(
    db: Session, technician_id: uuid.UUID, data: TechnicianUpdate
) -> Optional[Technician]:
    """Apply partial updates to a technician record."""
    tech = get_technician(db, technician_id)
    if not tech:
        return None

    # Fields that are NOT NULL in the DB — skip if value is None to avoid DB constraint errors
    NON_NULLABLE = {"name", "max_daily_calls", "is_available", "is_active", "role"}

    updates = data.model_dump(exclude_unset=True)

    # Handle password reset separately — hash before storing
    if "password" in updates:
        raw_password = updates.pop("password")
        if raw_password:
            tech.hashed_password = hash_password(raw_password)

    for field, value in updates.items():
        if value is None and field in NON_NULLABLE:
            continue   # ignore None for required fields (e.g. NumberInput cleared in UI)
        setattr(tech, field, value)

    db.commit()
    db.refresh(tech)
    return tech


def update_location(
    db: Session, technician_id: uuid.UUID, latitude: float, longitude: float
) -> Optional[Technician]:
    """Update a technician's real-time GPS location."""
    tech = get_technician(db, technician_id)
    if not tech:
        return None
    tech.current_latitude = latitude
    tech.current_longitude = longitude
    db.commit()
    db.refresh(tech)
    return tech


def get_technician_stats(db: Session, technician_id: uuid.UUID) -> Optional[TechnicianStats]:
    """Compute performance statistics for a technician.

    Returns:
        TechnicianStats or None if the technician does not exist.
    """
    tech = get_technician(db, technician_id)
    if not tech:
        return None

    assignments = (
        db.query(Assignment)
        .filter(Assignment.technician_id == technician_id)
        .all()
    )

    call_ids = [a.service_call_id for a in assignments]
    calls = (
        db.query(ServiceCall)
        .filter(ServiceCall.id.in_(call_ids))
        .all()
    ) if call_ids else []

    resolved = [c for c in calls if c.resolved_at]
    total_hours = sum(
        (c.resolved_at - c.created_at).total_seconds() / 3600
        for c in resolved
        if c.resolved_at and c.created_at
    )
    avg_hours = round(total_hours / len(resolved), 2) if resolved else None

    today = date.today()
    month_start = today.replace(day=1)

    calls_today = sum(
        1 for a in assignments
        if a.assigned_at and a.assigned_at.date() == today
    )
    calls_month = sum(
        1 for a in assignments
        if a.assigned_at and a.assigned_at.date() >= month_start
    )

    return TechnicianStats(
        technician_id=technician_id,
        total_calls_assigned=len(assignments),
        total_calls_resolved=len(resolved),
        avg_resolution_hours=avg_hours,
        calls_today=calls_today,
        calls_this_month=calls_month,
    )
