"""Inspection report endpoints."""
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from app.auth.dependencies import require_dispatcher_or_admin, get_current_user
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inspections", tags=["Inspections"])

ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/heic", "image/heif",
}


@router.post("/upload", summary="Upload and process an inspection report (PDF or image)")
def upload_inspection(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    content_type = file.content_type or ""
    # Normalize content type
    if content_type in ("image/jpg",):
        content_type = "image/jpeg"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"סוג קובץ לא נתמך: {content_type}. השתמש ב-PDF, JPEG, PNG או WEBP.",
        )
    file_bytes = file.file.read()
    if len(file_bytes) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=413, detail="הקובץ גדול מדי (מקסימום 20MB)")

    from app.services.inspection_service import process_inspection_report
    result = process_inspection_report(
        db,
        file_bytes=file_bytes,
        mime_type=content_type,
        file_name=file.filename or "",
        source="upload",
    )
    return result


@router.get("", summary="List recent inspection reports")
def list_inspections(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.inspection_report import InspectionReport
    from app.models.elevator import Elevator

    reports = (
        db.query(InspectionReport)
        .order_by(InspectionReport.processed_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
        .all()
    )

    result = []
    for r in reports:
        elevator = db.query(Elevator).filter(Elevator.id == r.elevator_id).first() if r.elevator_id else None
        suggested = db.query(Elevator).filter(Elevator.id == r.suggested_elevator_id).first() if r.suggested_elevator_id else None
        result.append({
            "id": str(r.id),
            "elevator_address": f"{elevator.address}, {elevator.city}" if elevator else r.raw_address or "לא ידוע",
            "elevator_id": str(r.elevator_id) if r.elevator_id else None,
            "suggested_elevator_id": str(r.suggested_elevator_id) if r.suggested_elevator_id else None,
            "suggested_elevator_address": f"{suggested.address}, {suggested.city}" if suggested else None,
            "raw_address": r.raw_address,
            "file_name": r.file_name,
            "inspection_date": r.inspection_date.isoformat() if r.inspection_date else None,
            "result": r.result,
            "deficiency_count": r.deficiency_count,
            "deficiencies": r.deficiencies,
            "inspector_name": r.inspector_name,
            "service_call_id": str(r.service_call_id) if r.service_call_id else None,
            "match_status": getattr(r, "match_status", "AUTO_MATCHED"),
            "match_score": getattr(r, "match_score", None),
            "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        })
    return result


@router.post("/{report_id}/confirm", summary="Confirm elevator match for a pending inspection report")
def confirm_inspection_match(
    report_id: str,
    elevator_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_dispatcher_or_admin),
):
    """
    Confirm (or override) the elevator match for a PENDING_REVIEW report.
    If elevator_id is provided, use that elevator. Otherwise use suggested_elevator_id.
    Triggers the same post-match logic (update last_service_date, open service call if needed).
    """
    import uuid as _uuid
    from app.models.inspection_report import InspectionReport
    from app.models.elevator import Elevator
    from app.services.inspection_service import _apply_inspection_to_elevator

    report = db.query(InspectionReport).filter(InspectionReport.id == _uuid.UUID(report_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    elev_id = _uuid.UUID(elevator_id) if elevator_id else report.suggested_elevator_id
    if not elev_id:
        raise HTTPException(status_code=400, detail="No elevator_id provided and no suggestion available")

    elevator = db.query(Elevator).filter(Elevator.id == elev_id).first()
    if not elevator:
        raise HTTPException(status_code=404, detail="Elevator not found")

    report.elevator_id = elevator.id
    report.match_status = "MANUALLY_CONFIRMED"
    db.commit()

    result = _apply_inspection_to_elevator(db, report, elevator)
    return {"ok": True, "elevator_address": f"{elevator.address}, {elevator.city}", **result}


@router.post("/{report_id}/reject", summary="Reject the suggested elevator match")
def reject_inspection_match(
    report_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    """Mark a PENDING_REVIEW report as UNMATCHED — dispatcher will handle manually."""
    import uuid as _uuid
    from app.models.inspection_report import InspectionReport

    report = db.query(InspectionReport).filter(InspectionReport.id == _uuid.UUID(report_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.match_status = "UNMATCHED"
    report.suggested_elevator_id = None
    db.commit()
    return {"ok": True}
