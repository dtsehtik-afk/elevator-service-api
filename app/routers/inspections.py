"""Inspection report endpoints."""
import logging
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
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
    elevator_id: Optional[str] = None,
    report_status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.inspection_report import InspectionReport
    from app.models.elevator import Elevator
    from app.models.technician import Technician

    q = db.query(InspectionReport)
    if elevator_id:
        q = q.filter(InspectionReport.elevator_id == uuid.UUID(elevator_id))
    if report_status:
        q = q.filter(InspectionReport.report_status == report_status)
    reports = q.order_by(InspectionReport.processed_at.desc()).offset(skip).limit(min(limit, 200)).all()

    result = []
    for r in reports:
        elevator = db.query(Elevator).filter(Elevator.id == r.elevator_id).first() if r.elevator_id else None
        suggested = db.query(Elevator).filter(Elevator.id == r.suggested_elevator_id).first() if r.suggested_elevator_id else None
        tech = db.query(Technician).filter(Technician.id == r.assigned_technician_id).first() if getattr(r, "assigned_technician_id", None) else None
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
            "file_url": f"/inspections/{r.id}/file" if getattr(r, "file_path", None) else None,
            "report_status": getattr(r, "report_status", "NA"),
            "assigned_technician_id": str(r.assigned_technician_id) if getattr(r, "assigned_technician_id", None) else None,
            "assigned_technician_name": tech.name if tech else None,
        })
    return result


@router.get("/search-elevators", summary="Search elevators by address for inspection matching")
def search_elevators_for_match(
    q: str = Query("", min_length=1),
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    from app.models.elevator import Elevator
    results = (
        db.query(Elevator)
        .filter(
            (Elevator.address.ilike(f"%{q}%")) |
            (Elevator.city.ilike(f"%{q}%")) |
            (Elevator.internal_number.ilike(f"%{q}%"))
        )
        .limit(10)
        .all()
    )
    return [
        {"id": str(e.id), "label": f"{e.address}, {e.city}" + (f" (#{e.internal_number})" if e.internal_number else "")}
        for e in results
    ]


@router.get("/{report_id}/file", summary="Download the original inspection report file")
def download_inspection_file(
    report_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.inspection_report import InspectionReport
    report = db.query(InspectionReport).filter(InspectionReport.id == uuid.UUID(report_id)).first()
    if not report or not getattr(report, "file_path", None):
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(report.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path, filename=report.file_name or path.name)


@router.post("/scan-emails", summary="Manually trigger Gmail inspection email scan (admin)")
def trigger_email_scan(
    since_days: int = Query(90, ge=1, le=365, description="How many days back to scan"),
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    """
    Manually trigger a scan of Gmail for inspection report emails.
    By default scans the last 90 days; use since_days to adjust.
    Emails are kept unread.
    """
    from datetime import date, timedelta
    from app.services.inspection_email_poller import poll_inspection_emails

    since = date.today() - timedelta(days=since_days)
    count = poll_inspection_emails(db, since_date=since)
    return {"reports_processed": count, "scanned_since": since.isoformat()}


@router.post("/claim/{report_id}", summary="Technician claims an open inspection report for remediation")
def claim_inspection_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.inspection_report import InspectionReport
    from app.models.technician import Technician

    report = db.query(InspectionReport).filter(InspectionReport.id == uuid.UUID(report_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if getattr(report, "report_status", "NA") not in ("OPEN", "PARTIAL"):
        raise HTTPException(status_code=400, detail="Report is not open for claiming")

    tech = db.query(Technician).filter(Technician.email == current_user.email).first()
    if not tech:
        raise HTTPException(status_code=400, detail="Technician record not found for this user")

    report.assigned_technician_id = tech.id
    db.commit()
    return {"ok": True, "technician_name": tech.name}


@router.patch("/checklist/{report_id}", summary="Update deficiency checklist items")
def update_checklist(
    report_id: str,
    updates: list,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    updates: list of {index: int, done: bool}
    When all items done → report_status = CLOSED; otherwise PARTIAL.
    """
    from app.models.inspection_report import InspectionReport

    report = db.query(InspectionReport).filter(InspectionReport.id == uuid.UUID(report_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    checklist = list(report.deficiencies or [])
    for upd in updates:
        idx = upd.get("index")
        if idx is not None and 0 <= idx < len(checklist):
            checklist[idx] = {**checklist[idx], "done": bool(upd.get("done", False))}

    report.deficiencies = checklist
    all_done = all(item.get("done", False) for item in checklist)
    any_done = any(item.get("done", False) for item in checklist)
    report.report_status = "CLOSED" if all_done else ("PARTIAL" if any_done else "OPEN")
    db.commit()
    return {"ok": True, "report_status": report.report_status}


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


@router.delete("/{report_id}", summary="Delete inspection report (admin only)")
def delete_inspection_report(
    report_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_dispatcher_or_admin),
):
    import uuid as _uuid
    from app.models.inspection_report import InspectionReport
    report = db.query(InspectionReport).filter(InspectionReport.id == _uuid.UUID(report_id)).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"ok": True}


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
