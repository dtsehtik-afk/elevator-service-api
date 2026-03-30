"""Router for daily schedule endpoint."""

import uuid
from datetime import date as date_module
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.technician import Technician
from app.services.schedule_service import build_daily_schedule

router = APIRouter()


@router.get(
    "/{technician_id}",
    summary="Daily schedule",
    description=(
        "Return the optimised daily schedule for a technician. "
        "Sorts stops by priority (CRITICAL first) then applies Nearest Neighbor "
        "within each priority group. Includes estimated arrival and duration per stop."
    ),
)
def get_daily_schedule(
    technician_id: uuid.UUID,
    date: Optional[str] = Query(None, description="Target date in YYYY-MM-DD format (defaults to today)"),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Build and return the optimised daily schedule for a technician."""
    try:
        target_date = date_module.fromisoformat(date) if date else date_module.today()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    schedule = build_daily_schedule(db, technician_id, target_date)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Technician not found")
    return schedule
