"""Control-plane admin endpoints — called by admin.lift-agent.com only.

Authentication: X-Control-Plane-Key header must match CONTROL_PLANE_API_KEY env var.
"""

import platform
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.elevator import Elevator
from app.models.service_call import ServiceCall
from app.models.system_settings import SystemSettings
from app.models.technician import Technician

router = APIRouter(prefix="/admin", tags=["Control Plane"])

_ALLOWED_MODULES = {
    "whatsapp",
    "email_calls",
    "inspection_emails",
    "google_drive",
    "openai_transcription",
    "maps",
    "whatsapp_reminders",
}

_startup_time = datetime.now(timezone.utc)


def _require_control_plane_key(x_control_plane_key: str = Header(...)):
    settings = get_settings()
    if not settings.control_plane_api_key:
        raise HTTPException(status_code=503, detail="Control plane not configured")
    if x_control_plane_key != settings.control_plane_api_key:
        raise HTTPException(status_code=401, detail="Invalid control plane key")


def _get_or_create_settings(db: Session) -> SystemSettings:
    row = db.query(SystemSettings).filter_by(key="default").first()
    if not row:
        row = SystemSettings(key="default", modules={m: True for m in _ALLOWED_MODULES})
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


# ── Stats ──────────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    elevators_total: int
    elevators_active: int
    calls_open: int
    calls_assigned: int
    calls_in_progress: int
    technicians_total: int
    technicians_active: int
    technicians_on_call: int
    uptime_seconds: int
    modules: dict


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(_require_control_plane_key)])
def get_stats(db: Session = Depends(get_db)):
    """Live metrics snapshot — polled every 5 minutes by the control plane."""
    elevators_total = db.query(func.count(Elevator.id)).scalar()
    elevators_active = db.query(func.count(Elevator.id)).filter(Elevator.status == "ACTIVE").scalar()

    calls_open = db.query(func.count(ServiceCall.id)).filter(ServiceCall.status == "OPEN").scalar()
    calls_assigned = db.query(func.count(ServiceCall.id)).filter(ServiceCall.status == "ASSIGNED").scalar()
    calls_in_progress = db.query(func.count(ServiceCall.id)).filter(ServiceCall.status == "IN_PROGRESS").scalar()

    technicians_total = db.query(func.count(Technician.id)).scalar()
    technicians_active = db.query(func.count(Technician.id)).filter(Technician.is_active == True).scalar()
    technicians_on_call = db.query(func.count(Technician.id)).filter(
        Technician.is_active == True,
        Technician.is_on_call == True,
    ).scalar()

    settings_row = _get_or_create_settings(db)
    uptime = int((datetime.now(timezone.utc) - _startup_time).total_seconds())

    return StatsResponse(
        elevators_total=elevators_total,
        elevators_active=elevators_active,
        calls_open=calls_open,
        calls_assigned=calls_assigned,
        calls_in_progress=calls_in_progress,
        technicians_total=technicians_total,
        technicians_active=technicians_active,
        technicians_on_call=technicians_on_call,
        uptime_seconds=uptime,
        modules=settings_row.modules,
    )


# ── Modules ────────────────────────────────────────────────────────────────────

class ModulesUpdate(BaseModel):
    modules: dict[str, bool]


class ModulesResponse(BaseModel):
    modules: dict


@router.post("/modules", response_model=ModulesResponse, dependencies=[Depends(_require_control_plane_key)])
def update_modules(body: ModulesUpdate, db: Session = Depends(get_db)):
    """Enable or disable feature modules. Unknown module names are rejected."""
    unknown = set(body.modules) - _ALLOWED_MODULES
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown modules: {sorted(unknown)}. Allowed: {sorted(_ALLOWED_MODULES)}",
        )

    row = _get_or_create_settings(db)
    row.modules = {**row.modules, **body.modules}
    db.commit()
    db.refresh(row)
    return ModulesResponse(modules=row.modules)


@router.get("/modules", response_model=ModulesResponse, dependencies=[Depends(_require_control_plane_key)])
def get_modules(db: Session = Depends(get_db)):
    """Return current module flags."""
    row = _get_or_create_settings(db)
    return ModulesResponse(modules=row.modules)


# ── Logs ───────────────────────────────────────────────────────────────────────

_startup_time_log = time.time()


@router.get("/logs", dependencies=[Depends(_require_control_plane_key)])
def list_logs(
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    from app.models.admin_log import AdminLog as AdminLogModel
    from app.services import admin_log_service

    logs = admin_log_service.list_logs(db, level=level, search=search, limit=limit)
    counts: dict = {}
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        counts[lvl] = db.query(AdminLogModel).filter(AdminLogModel.level == lvl).count()

    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return {
        "logs": [
            {
                "id": str(log.id),
                "level": log.level,
                "source": log.source,
                "message": log.message,
                "stack_trace": log.stack_trace,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "counts": counts,
        "health": {
            "db_ok": db_ok,
            "uptime_seconds": round(time.time() - _startup_time_log, 1),
            "python_version": platform.python_version(),
            "server_time": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.delete("/logs", dependencies=[Depends(_require_control_plane_key)])
def clear_logs(
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from app.services import admin_log_service

    count = admin_log_service.clear_logs(db, level=level)
    return {"deleted": count}
