"""Admin Console router — error log viewer + module toggles (ADMIN only)."""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.admin_log import AdminLog
from app.models.technician import Technician
from app.services import admin_log_service

router = APIRouter(prefix="/admin-console", tags=["admin-console"])

_START_TIME = time.time()


# ─── Schemas ────────────────────────────────────────────────────────────────

class AdminLogResponse(BaseModel):
    id: str
    level: str
    source: Optional[str]
    message: str
    stack_trace: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ModuleSettings(BaseModel):
    whatsapp: bool = True
    email_calls: bool = True
    google_drive: bool = False
    after_hours: bool = True
    ai_assignment: bool = True
    inspection_emails: bool = True
    sms_alerts: bool = False


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    db_ok: bool
    python_version: str
    server_time: datetime
    log_counts: dict


class WriteLogRequest(BaseModel):
    level: str = "INFO"
    source: str = "manual"
    message: str


# ─── Health ─────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
def get_health(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    db_ok = True
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_ok = False

    counts = {}
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        counts[lvl] = db.query(AdminLog).filter(AdminLog.level == lvl).count()

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        uptime_seconds=round(time.time() - _START_TIME, 1),
        db_ok=db_ok,
        python_version=platform.python_version(),
        server_time=datetime.now(timezone.utc),
        log_counts=counts,
    )


# ─── Logs ───────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[AdminLogResponse])
def get_logs(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    logs = admin_log_service.list_logs(db, level=level, source=source, search=search, skip=skip, limit=limit)
    return [
        AdminLogResponse(
            id=str(log.id),
            level=log.level,
            source=log.source,
            message=log.message,
            stack_trace=log.stack_trace,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.post("/logs", response_model=AdminLogResponse, status_code=201)
def write_log(
    body: WriteLogRequest,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    """Manually write a test log entry (useful for verifying the log pipeline)."""
    entry = admin_log_service.log_event(db, body.message, level=body.level, source=body.source)
    return AdminLogResponse(
        id=str(entry.id),
        level=entry.level,
        source=entry.source,
        message=entry.message,
        stack_trace=entry.stack_trace,
        created_at=entry.created_at,
    )


@router.delete("/logs")
def clear_logs(
    level: Optional[str] = Query(None, description="Clear only this level; omit to clear all"),
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    count = admin_log_service.clear_logs(db, level=level)
    return {"deleted": count}


# ─── Module Toggles ─────────────────────────────────────────────────────────

def _get_settings(db: Session):
    from app.models.system_settings import SystemSettings
    obj = db.query(SystemSettings).filter(SystemSettings.key == "default").first()
    if not obj:
        obj = SystemSettings(key="default", modules={})
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj


@router.get("/modules", response_model=dict)
def get_modules(
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    obj = _get_settings(db)
    defaults = ModuleSettings().model_dump()
    defaults.update(obj.modules or {})
    return defaults


@router.put("/modules", response_model=dict)
def update_modules(
    body: dict,
    db: Session = Depends(get_db),
    _: Technician = Depends(require_admin),
):
    obj = _get_settings(db)
    current = dict(obj.modules or {})
    current.update(body)
    obj.modules = current
    db.commit()
    db.refresh(obj)
    defaults = ModuleSettings().model_dump()
    defaults.update(obj.modules)
    return defaults
