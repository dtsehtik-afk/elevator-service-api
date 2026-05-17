"""Activity log router — recent system events feed."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.activity_log import ActivityLog
from app.models.technician import Technician
from app.schemas.activity_log import ActivityLogResponse

router = APIRouter(prefix="/activity-log", tags=["Activity"])


@router.get("", response_model=List[ActivityLogResponse])
def list_activity(
    category: Optional[str] = Query(None, description="Filter by category: service | finance"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
    if category:
        q = q.filter(ActivityLog.category == category)
    return q.limit(limit).all()
