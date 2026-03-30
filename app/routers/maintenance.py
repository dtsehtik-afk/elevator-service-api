"""Router for maintenance schedule CRUD endpoints."""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_dispatcher_or_admin
from app.database import get_db
from app.models.technician import Technician
from app.schemas.maintenance import MaintenanceCreate, MaintenanceResponse, MaintenanceUpdate
from app.services import maintenance_service

router = APIRouter()


@router.get(
    "",
    response_model=List[MaintenanceResponse],
    summary="List maintenance schedules",
    description="Return filtered maintenance schedules.",
)
def list_maintenances(
    elevator_id: Optional[uuid.UUID] = Query(None),
    technician_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None, description="SCHEDULED|COMPLETED|OVERDUE|CANCELLED"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List maintenance events with optional filters."""
    return maintenance_service.list_maintenances(
        db, elevator_id, technician_id, status, from_date, to_date, skip, limit
    )


@router.post(
    "",
    response_model=MaintenanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule maintenance",
    description="Create a new maintenance event. Requires ADMIN or DISPATCHER.",
)
def create_maintenance(
    data: MaintenanceCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_dispatcher_or_admin),
):
    """Schedule a maintenance event for an elevator."""
    from app.services.elevator_service import get_elevator
    if not get_elevator(db, data.elevator_id):
        raise HTTPException(status_code=404, detail="Elevator not found")
    return maintenance_service.create_maintenance(db, data)


@router.get(
    "/{maintenance_id}",
    response_model=MaintenanceResponse,
    summary="Get maintenance event",
)
def get_maintenance(
    maintenance_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Fetch a single maintenance event by ID."""
    m = maintenance_service.get_maintenance(db, maintenance_id)
    if not m:
        raise HTTPException(status_code=404, detail="Maintenance event not found")
    return m


@router.patch(
    "/{maintenance_id}",
    response_model=MaintenanceResponse,
    summary="Update maintenance event",
    description="Update status, checklist, or notes. Requires ADMIN or DISPATCHER.",
)
def update_maintenance(
    maintenance_id: uuid.UUID,
    data: MaintenanceUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_dispatcher_or_admin),
):
    """Update a maintenance event."""
    m = maintenance_service.update_maintenance(db, maintenance_id, data)
    if not m:
        raise HTTPException(status_code=404, detail="Maintenance event not found")
    return m
