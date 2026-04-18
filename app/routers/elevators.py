"""Router for elevator CRUD and analytics endpoints."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.technician import Technician
from app.schemas.elevator import ElevatorAnalytics, ElevatorCreate, ElevatorResponse, ElevatorUpdate
from app.schemas.service_call import ServiceCallResponse
from app.services import elevator_service

router = APIRouter()


@router.get(
    "",
    response_model=List[ElevatorResponse],
    summary="List elevators",
    description="Return a paginated, filtered list of elevators. Requires authentication.",
)
def list_elevators(
    city: Optional[str] = Query(None, description="Filter by city (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE | INACTIVE | UNDER_REPAIR"),
    min_risk: Optional[float] = Query(None, ge=0, le=100, description="Minimum risk score"),
    max_risk: Optional[float] = Query(None, ge=0, le=100, description="Maximum risk score"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List elevators with optional filters."""
    return elevator_service.list_elevators(db, city, status, min_risk, max_risk, skip, limit)


@router.post(
    "",
    response_model=ElevatorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create elevator",
    description="Add a new elevator to the system. Requires ADMIN or DISPATCHER role.",
)
def create_elevator(
    data: ElevatorCreate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Create a new elevator record."""
    from app.auth.dependencies import require_roles
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Admin or Dispatcher access required")
    return elevator_service.create_elevator(db, data)


@router.get(
    "/{elevator_id}",
    response_model=ElevatorResponse,
    summary="Get elevator",
    description="Return full details of a single elevator.",
)
def get_elevator(
    elevator_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Fetch a single elevator by ID."""
    elevator = elevator_service.get_elevator(db, elevator_id)
    if not elevator:
        raise HTTPException(status_code=404, detail="Elevator not found")
    return elevator


@router.put(
    "/{elevator_id}",
    response_model=ElevatorResponse,
    summary="Update elevator",
    description="Update elevator details. Requires ADMIN or DISPATCHER role.",
)
def update_elevator(
    elevator_id: uuid.UUID,
    data: ElevatorUpdate,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Update an existing elevator's details."""
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Admin or Dispatcher access required")
    elevator = elevator_service.update_elevator(db, elevator_id, data)
    if not elevator:
        raise HTTPException(status_code=404, detail="Elevator not found")
    return elevator


@router.get(
    "/{elevator_id}/analytics",
    response_model=ElevatorAnalytics,
    summary="Elevator analytics",
    description="Fault breakdown and recurring call analysis for a specific elevator.",
)
def get_elevator_analytics(
    elevator_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return analytics for a specific elevator."""
    analytics = elevator_service.get_elevator_analytics(db, elevator_id)
    if not analytics:
        raise HTTPException(status_code=404, detail="Elevator not found")
    return analytics


@router.get(
    "/{elevator_id}/calls",
    response_model=List[ServiceCallResponse],
    summary="Elevator service call history",
    description="Return all service calls for a specific elevator.",
)
def get_elevator_calls(
    elevator_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """Return service call history for an elevator."""
    elevator = elevator_service.get_elevator(db, elevator_id)
    if not elevator:
        raise HTTPException(status_code=404, detail="Elevator not found")
    from app.services.service_call_service import list_service_calls
    return list_service_calls(db, elevator_id=elevator_id, limit=200)


@router.post(
    "/import-excel",
    summary="Import elevators from Excel",
    description="Upload an .xlsx report and import elevator data. Requires ADMIN or DISPATCHER role.",
)
async def import_elevators_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Parse an Excel elevator report and upsert records into the database."""
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Admin or Dispatcher access required")

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="יש להעלות קובץ Excel בלבד (.xlsx)")

    excel_bytes = await file.read()
    if not excel_bytes:
        raise HTTPException(status_code=400, detail="הקובץ ריק")

    try:
        from app.services.excel_import_service import import_elevators_from_excel
        stats = import_elevators_from_excel(db, excel_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"שגיאה בפענוח הקובץ: {exc}")

    return stats


@router.post(
    "/import-pdf",
    summary="Import elevators from PDF",
    description="Upload a PDF report and import elevator data. Requires ADMIN or DISPATCHER role.",
)
async def import_elevators_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Parse a PDF elevator report and upsert records into the database."""
    if current_user.role not in ("ADMIN", "DISPATCHER"):
        raise HTTPException(status_code=403, detail="Admin or Dispatcher access required")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="יש להעלות קובץ PDF בלבד")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="הקובץ ריק")

    try:
        from app.services.pdf_import_service import import_elevators_from_pdf
        stats = import_elevators_from_pdf(db, pdf_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"שגיאה בפענוח ה-PDF: {exc}")

    return stats


@router.post(
    "/{elevator_id}/upload-file",
    summary="Upload a file (agreement or inspection report) for an elevator",
)
async def upload_elevator_file(
    elevator_id: uuid.UUID,
    field: str = Query(..., description="drive_link | last_inspection_report_url"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Store uploaded PDF/image and save its URL on the elevator record."""
    from pathlib import Path

    if field not in ("drive_link", "last_inspection_report_url"):
        raise HTTPException(status_code=400, detail=f"Unknown field: {field}")

    upload_dir = Path("uploads/elevators")
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "file").suffix or ".pdf"
    filename = f"{elevator_id}_{field}_{uuid.uuid4().hex[:8]}{ext}"
    (upload_dir / filename).write_bytes(await file.read())

    url = f"/uploads/elevators/{filename}"

    elev = db.query(elevator_service.Elevator).filter_by(id=elevator_id).first()
    if not elev:
        raise HTTPException(status_code=404, detail="Elevator not found")

    setattr(elev, field, url)
    db.commit()
    return {"url": url, "field": field}
