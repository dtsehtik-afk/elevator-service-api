"""Router for analytics and reporting endpoints — ADMIN only."""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.technician import Technician
from app.services.analytics_service import (
    export_calls_excel,
    get_elevator_history,
    get_monthly_summary,
    get_recurring_fault_elevators,
    get_risk_elevators,
    get_technician_performance,
)

router = APIRouter()


@router.get(
    "/recurring-faults",
    summary="Recurring fault elevators",
    description="Return elevators with 3 or more service calls in the last 90 days. ADMIN only.",
)
def recurring_faults(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> List[Dict[str, Any]]:
    """List elevators with 3+ service calls in the past 90 days."""
    return get_recurring_fault_elevators(db)


@router.get(
    "/technician-performance",
    summary="Technician performance",
    description="Average resolution time and call counts per technician. ADMIN only.",
)
def technician_performance(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> List[Dict[str, Any]]:
    """Return performance metrics for every technician."""
    return get_technician_performance(db)


@router.get(
    "/monthly-summary",
    summary="Monthly summary",
    description="Aggregated statistics for a given month: total calls, resolved, averages. ADMIN only.",
)
def monthly_summary(
    year: int = Query(..., ge=2020, le=2100, description="Year (e.g. 2024)"),
    month: int = Query(..., ge=1, le=12, description="Month number (1-12)"),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> Dict[str, Any]:
    """Return a monthly summary of service activity."""
    return get_monthly_summary(db, year, month)


@router.get(
    "/risk-elevators",
    summary="High-risk elevators",
    description="Return elevators with risk_score > 70. ADMIN only.",
)
def risk_elevators(
    threshold: float = Query(70.0, ge=0, le=100, description="Minimum risk score"),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> List[Dict[str, Any]]:
    """Return elevators whose risk score exceeds the given threshold."""
    return get_risk_elevators(db, threshold)


@router.get(
    "/elevator/{elevator_id}/history",
    summary="Elevator call history",
    description="Full service call history for a specific elevator.",
)
def elevator_history(
    elevator_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> Dict[str, Any]:
    """Return all service calls for a given elevator, newest first."""
    return get_elevator_history(db, elevator_id)


@router.get(
    "/export/excel",
    summary="Export service calls to Excel",
    description="Download a .xlsx report of service calls. Filter by date range or elevator.",
)
def export_excel(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to:   Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    elevator_id: Optional[uuid.UUID] = Query(None, description="Filter by elevator"),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """Export filtered service calls as an Excel file."""
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc) if date_from else None
    dt_to   = datetime(date_to.year,   date_to.month,   date_to.day,   23, 59, 59, tzinfo=timezone.utc) if date_to else None

    xlsx_bytes = export_calls_excel(db, dt_from, dt_to, elevator_id)

    filename = "service_calls"
    if date_from:
        filename += f"_{date_from}"
    if date_to:
        filename += f"_to_{date_to}"
    filename += ".xlsx"

    import io
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
