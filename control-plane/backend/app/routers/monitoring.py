"""Monitoring — health snapshots per tenant."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.database import get_db
from app.models.tenant import Tenant
from app.models.tenant_snapshot import TenantSnapshot

router = APIRouter(prefix="/tenants/{tenant_id}/monitoring", tags=["Monitoring"])


class SnapshotOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    captured_at: datetime
    is_healthy: bool
    stats: dict | None
    error: str | None

    class Config:
        from_attributes = True


class TenantHealthOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    status: str
    is_healthy: bool
    last_seen_at: datetime | None
    last_stats: dict | None


@router.get("", response_model=list[SnapshotOut])
def get_snapshots(
    tenant_id: uuid.UUID,
    limit: int = 48,  # ~4h at 5-min intervals
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return (
        db.query(TenantSnapshot)
        .filter_by(tenant_id=tenant_id)
        .order_by(TenantSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/poll", response_model=SnapshotOut)
def poll_now(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Trigger an immediate health poll for a single tenant."""
    from app.services.monitor import poll_tenant
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    snapshot = poll_tenant(tenant, db)
    return snapshot


# ── Global health overview ─────────────────────────────────────────────────────

overview_router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@overview_router.get("/overview", response_model=list[TenantHealthOut])
def health_overview(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Current health of all tenants — one row per tenant."""
    tenants = db.query(Tenant).order_by(Tenant.name).all()
    return [
        TenantHealthOut(
            tenant_id=t.id,
            tenant_name=t.name,
            status=t.status,
            is_healthy=t.is_healthy,
            last_seen_at=t.last_seen_at,
            last_stats=t.last_stats,
        )
        for t in tenants
    ]
