"""Router for technician management endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.technician import Technician
from app.schemas.technician import (
    LocationUpdate,
    TechnicianCreate,
    TechnicianResponse,
    TechnicianStats,
    TechnicianUpdate,
)
from app.services import technician_service

router = APIRouter()


@router.get(
    "",
    response_model=List[TechnicianResponse],
    summary="List technicians",
    description="Return all technicians. Requires authentication.",
)
def list_technicians(
    is_available: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List technicians with optional availability filters."""
    return technician_service.list_technicians(db, is_available, is_active, skip, limit)


@router.post(
    "",
    response_model=TechnicianResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create technician",
    description="Create a new technician account. ADMIN only.",
)
def create_technician(
    data: TechnicianCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """Create a new technician — admin only."""
    try:
        return technician_service.create_technician(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{technician_id}",
    response_model=TechnicianResponse,
    summary="Get technician",
    description="Return details of a specific technician.",
)
def get_technician(
    technician_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Fetch a single technician by ID."""
    tech = technician_service.get_technician(db, technician_id)
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    return tech


@router.put(
    "/{technician_id}",
    response_model=TechnicianResponse,
    summary="Update technician",
    description="Update technician details. ADMIN only.",
)
def update_technician(
    technician_id: uuid.UUID,
    data: TechnicianUpdate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Update a technician — admins can update anyone, technicians can only update themselves."""
    if current_user.role != "ADMIN" and current_user.id != technician_id:
        raise HTTPException(status_code=403, detail="You can only update your own profile")
    tech = technician_service.update_technician(db, technician_id, data)
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    return tech


@router.post(
    "/location",
    response_model=TechnicianResponse,
    summary="Update location",
    description="Update the authenticated technician's real-time GPS location.",
)
def update_location(
    data: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Update the current technician's location — uses the authenticated user's ID."""
    tech = technician_service.update_location(
        db, current_user.id, data.latitude, data.longitude
    )
    return tech


@router.patch(
    "/{technician_id}/on-call",
    response_model=TechnicianResponse,
    summary="Set on-call technician",
    description="Designate a single technician as on-call. ADMIN only.",
)
def set_on_call(
    technician_id: uuid.UUID,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """Clear is_on_call on all technicians, then set it on the target one."""
    # Clear is_on_call on all technicians first
    db.query(Technician).update({Technician.is_on_call: False})
    # Set on the target
    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    if payload.get("is_on_call", True):
        tech.is_on_call = True
    db.commit()
    db.refresh(tech)
    return tech


@router.get(
    "/{technician_id}/stats",
    response_model=TechnicianStats,
    summary="Technician stats",
    description="Return performance statistics for a technician.",
)
def get_stats(
    technician_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return performance stats for a specific technician."""
    stats = technician_service.get_technician_stats(db, technician_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Technician not found")
    return stats


@router.get(
    "/{technician_id}/schedule",
    summary="Technician daily schedule",
    description="Return the daily schedule for a technician. See /schedule/{id} for the full algorithm.",
)
def get_schedule(
    technician_id: uuid.UUID,
    date: Optional[str] = Query(None, description="YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return daily schedule — delegates to the schedule service."""
    from app.services.schedule_service import build_daily_schedule
    from datetime import date as date_type
    target_date = date_type.fromisoformat(date) if date else date_type.today()
    result = build_daily_schedule(db, technician_id, target_date)
    if result is None:
        raise HTTPException(status_code=404, detail="Technician not found")
    return result


@router.delete(
    "/{technician_id}",
    status_code=200,
    summary="Delete technician (admin only)",
)
def delete_technician(
    technician_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(require_admin),
):
    tech = db.query(Technician).filter(Technician.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    db.delete(tech)
    db.commit()
    return {"ok": True}
