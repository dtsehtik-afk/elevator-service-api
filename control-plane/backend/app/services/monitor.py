"""Background monitor — polls every tenant's /health and /admin/stats every N minutes."""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.tenant import Tenant
from app.models.tenant_snapshot import TenantSnapshot

logger = logging.getLogger(__name__)
_TIMEOUT = 8.0
_scheduler = None


def poll_tenant(tenant: Tenant, db: Session) -> TenantSnapshot:
    """
    Poll /health then /admin/stats for a single tenant.
    Writes a TenantSnapshot row and updates tenant.is_healthy / last_seen_at / last_stats.
    Returns the snapshot.
    """
    snapshot = TenantSnapshot(tenant_id=tenant.id, is_healthy=False)

    if not tenant.api_url:
        snapshot.error = "no api_url configured"
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    base = tenant.api_url.rstrip("/")
    headers = {"X-Control-Plane-Key": tenant.api_key}

    try:
        # 1. Health check
        health = httpx.get(f"{base}/health", timeout=_TIMEOUT)
        if health.status_code != 200:
            raise ValueError(f"/health returned {health.status_code}")

        # 2. Stats
        stats_resp = httpx.get(f"{base}/admin/stats", headers=headers, timeout=_TIMEOUT)
        stats_resp.raise_for_status()
        stats = stats_resp.json()

        snapshot.is_healthy = True
        snapshot.stats = stats

        tenant.is_healthy = True
        tenant.last_seen_at = datetime.now(timezone.utc)
        tenant.last_stats = stats

        # Sync module cache
        if "modules" in stats:
            tenant.modules = stats["modules"]

    except Exception as exc:
        snapshot.is_healthy = False
        snapshot.error = str(exc)[:500]
        tenant.is_healthy = False
        logger.warning("Health check failed for tenant %s (%s): %s", tenant.slug, base, exc)

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def _poll_all():
    """Called by APScheduler — polls every ACTIVE tenant."""
    db: Session = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.status == "ACTIVE").all()
        logger.debug("Polling %d active tenants", len(tenants))
        for tenant in tenants:
            try:
                poll_tenant(tenant, db)
            except Exception as exc:
                logger.exception("Unhandled error polling tenant %s: %s", tenant.slug, exc)
    finally:
        db.close()


def start_monitor():
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.config import get_settings

    interval = get_settings().monitor_interval_seconds
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_poll_all, "interval", seconds=interval, id="monitor_all_tenants")
    _scheduler.start()
    logger.info("Monitor started — polling every %ds", interval)


def stop_monitor():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
