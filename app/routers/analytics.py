"""Router for analytics and reporting endpoints — ADMIN only."""

import uuid
from datetime import date, datetime, timedelta, timezone
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


@router.get("/financial-summary", summary="Outstanding debt and aging breakdown. ADMIN only.")
def financial_summary(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> Dict[str, Any]:
    """Return unpaid invoice totals grouped by aging bucket (0-30, 31-60, 61+ days overdue)."""
    from app.models.invoice import Invoice
    today = date.today()

    unpaid = db.query(Invoice).filter(
        Invoice.status.in_(["SENT", "PARTIAL", "OVERDUE"])
    ).all()

    def _overdue_days(inv: Invoice) -> int:
        if inv.due_date is None:
            return 0
        return max(0, (today - inv.due_date).days)

    def _balance(inv: Invoice) -> float:
        return max(0.0, float(inv.total) - float(inv.amount_paid))

    total = sum(_balance(i) for i in unpaid)
    aging_30 = sum(_balance(i) for i in unpaid if _overdue_days(i) <= 30)
    aging_60 = sum(_balance(i) for i in unpaid if 30 < _overdue_days(i) <= 60)
    aging_90 = sum(_balance(i) for i in unpaid if _overdue_days(i) > 60)

    return {
        "total_outstanding": round(total, 2),
        "aging_0_30": round(aging_30, 2),
        "aging_31_60": round(aging_60, 2),
        "aging_61_plus": round(aging_90, 2),
        "invoice_count": len(unpaid),
    }


@router.get("/safety-summary", summary="Inspection and deficiency status. ADMIN only.")
def safety_summary(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
) -> Dict[str, Any]:
    """Return upcoming inspections, overdue inspections, and open deficiency reports."""
    from app.models.elevator import Elevator
    from app.models.inspection_report import InspectionReport
    today = date.today()
    in_30 = today + timedelta(days=30)

    due_soon = db.query(Elevator).filter(
        Elevator.next_inspection_date.isnot(None),
        Elevator.next_inspection_date > today,
        Elevator.next_inspection_date <= in_30,
    ).count()

    overdue = db.query(Elevator).filter(
        Elevator.next_inspection_date.isnot(None),
        Elevator.next_inspection_date < today,
    ).count()

    open_reports = db.query(InspectionReport).filter(
        InspectionReport.report_status.in_(["OPEN", "PARTIAL"])
    ).count()

    no_date = db.query(Elevator).filter(
        Elevator.next_inspection_date.is_(None),
        Elevator.status == "ACTIVE",
    ).count()

    return {
        "due_in_30_days": due_soon,
        "overdue_inspections": overdue,
        "open_deficiency_reports": open_reports,
        "no_inspection_date": no_date,
    }
