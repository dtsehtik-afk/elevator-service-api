"""Monitoring — health snapshots per tenant + admin console proxy."""

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.database import get_db
from app.models.tenant import Tenant
from app.models.tenant_snapshot import TenantSnapshot

_PROXY_TIMEOUT = 10.0

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


@router.get("/console")
async def get_console(
    tenant_id: uuid.UUID,
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Proxy to the tenant's /admin/logs endpoint (requires X-Control-Plane-Key)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.api_url or not tenant.api_key:
        raise HTTPException(status_code=422, detail="Tenant has no api_url or api_key")

    url = tenant.api_url.rstrip("/") + "/admin/logs"
    params = {"limit": limit}
    if level:
        params["level"] = level
    if search:
        params["search"] = search

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            r = await client.get(url, headers={"X-Control-Plane-Key": tenant.api_key}, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Tenant returned {r.status_code}")
        return r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tenant did not respond in time")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.delete("/console/logs")
async def clear_console_logs(
    tenant_id: uuid.UUID,
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Proxy DELETE /admin/logs on the tenant."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.api_url or not tenant.api_key:
        raise HTTPException(status_code=422, detail="Tenant has no api_url or api_key")

    url = tenant.api_url.rstrip("/") + "/admin/logs"
    params = {}
    if level:
        params["level"] = level

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            r = await client.delete(url, headers={"X-Control-Plane-Key": tenant.api_key}, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Tenant returned {r.status_code}")
        return r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tenant did not respond in time")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
