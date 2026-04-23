import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tenant import Tenant
from app.auth.dependencies import get_current_admin

router = APIRouter(prefix="/stats", tags=["stats"])

TIMEOUT = 8.0


async def _fetch_tenant_stats(tenant: Tenant) -> dict:
    if not tenant.api_url or not tenant.api_key:
        return {"error": "not_configured"}
    url = tenant.api_url.rstrip("/") + "/admin/stats"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, headers={"X-Admin-Key": tenant.api_key})
        if r.status_code == 200:
            return r.json()
        return {"error": f"http_{r.status_code}"}
    except httpx.TimeoutException:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/all")
async def all_stats(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    """Fetch stats from all active tenants concurrently."""
    import asyncio
    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    tasks = [_fetch_tenant_stats(t) for t in tenants]
    results = await asyncio.gather(*tasks)
    return [
        {"tenant_id": str(t.id), "slug": t.slug, "name": t.name, "stats": s}
        for t, s in zip(tenants, results)
    ]


@router.get("/{tenant_id}")
async def tenant_stats(tenant_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    import uuid as _uuid
    t = db.query(Tenant).filter(Tenant.id == _uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    stats = await _fetch_tenant_stats(t)
    # Cache in DB
    if "error" not in stats:
        t.stats = stats
        t.stats_refreshed_at = datetime.now(timezone.utc)
        db.commit()
    return stats


@router.post("/{tenant_id}/ping")
async def ping_tenant(tenant_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    import uuid as _uuid
    t = db.query(Tenant).filter(Tenant.id == _uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if not t.api_url:
        raise HTTPException(status_code=422, detail="api_url not set")
    url = t.api_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
        alive = r.status_code < 500
    except Exception:
        alive = False
    if alive:
        t.last_seen_at = datetime.now(timezone.utc)
        db.commit()
    return {"alive": alive}
