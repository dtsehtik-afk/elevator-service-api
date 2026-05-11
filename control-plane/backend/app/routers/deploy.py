"""1-click tenant deployment via Hetzner Cloud API."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/tenants/{tenant_id}/deploy", tags=["Deploy"])


class DeployRequest(BaseModel):
    db_password: str        # password for tenant's PostgreSQL
    secret_key: str         # JWT secret for tenant app
    gemini_api_key: str = ""
    gmail_user_calls: str = ""
    gmail_app_password_calls: str = ""
    greenapi_instance_id: str = ""
    greenapi_api_token: str = ""
    google_maps_api_key: str = ""


class DeployStatus(BaseModel):
    tenant_id: uuid.UUID
    status: str
    hetzner_server_id: int | None
    hetzner_server_ip: str | None
    api_url: str | None
    message: str


@router.post("", response_model=DeployStatus)
def deploy_tenant(
    tenant_id: uuid.UUID,
    body: DeployRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """
    Provision a new Hetzner VPS for this tenant and run docker-compose.
    The server creation is async — status goes DEPLOYING → ACTIVE (or ERROR).
    """
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "ACTIVE":
        raise HTTPException(status_code=409, detail="Tenant already deployed")
    if tenant.status == "DEPLOYING":
        raise HTTPException(status_code=409, detail="Deploy already in progress")

    tenant.status = "DEPLOYING"
    db.commit()

    background_tasks.add_task(_do_deploy, tenant_id=tenant_id, body=body)

    return DeployStatus(
        tenant_id=tenant_id,
        status="DEPLOYING",
        hetzner_server_id=None,
        hetzner_server_ip=None,
        api_url=None,
        message="Server provisioning started — poll /status for updates",
    )


@router.post("/ssl", response_model=DeployStatus)
def provision_ssl(
    tenant_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """
    SSH into the tenant server and run certbot to issue an SSL certificate.
    Requires the server to be ACTIVE and DNS to be propagated.
    """
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status != "ACTIVE" or not tenant.hetzner_server_ip:
        raise HTTPException(status_code=409, detail="Tenant not active or no IP")

    background_tasks.add_task(_run_certbot, tenant.hetzner_server_ip, tenant.slug)
    return DeployStatus(
        tenant_id=tenant_id,
        status=tenant.status,
        hetzner_server_id=tenant.hetzner_server_id,
        hetzner_server_ip=tenant.hetzner_server_ip,
        api_url=tenant.api_url,
        message="Certbot triggered — SSL will be ready in ~30 seconds",
    )


def _run_certbot(ip: str, slug: str):
    """SSH into the server and run certbot. Requires SSH key access."""
    import subprocess, logging
    domain = f"{slug}.lift-agent.com"
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"root@{ip}",
        f"certbot --nginx -d {domain} --non-interactive --agree-tos -m admin@lift-agent.com",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        logging.getLogger(__name__).info("SSL issued for %s", domain)
    else:
        logging.getLogger(__name__).error("Certbot failed for %s: %s", domain, result.stderr)


@router.get("/status", response_model=DeployStatus)
def deploy_status(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return DeployStatus(
        tenant_id=tenant_id,
        status=tenant.status,
        hetzner_server_id=tenant.hetzner_server_id,
        hetzner_server_ip=tenant.hetzner_server_ip,
        api_url=tenant.api_url,
        message="",
    )


@router.delete("", response_model=DeployStatus)
def destroy_server(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Delete the Hetzner server. Tenant data is NOT deleted from the registry."""
    from app.services.hetzner import delete_server
    from app.services.cloudflare import _delete_by_name

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.hetzner_server_id:
        raise HTTPException(status_code=409, detail="No server to destroy")

    delete_server(tenant.hetzner_server_id)
    try:
        _delete_by_name(f"{tenant.slug}.lift-agent.com")
    except Exception:
        pass
    tenant.hetzner_server_id = None
    tenant.hetzner_server_ip = None
    tenant.api_url = None
    tenant.status = "SUSPENDED"
    tenant.is_healthy = False
    db.commit()

    return DeployStatus(
        tenant_id=tenant_id,
        status="SUSPENDED",
        hetzner_server_id=None,
        hetzner_server_ip=None,
        api_url=None,
        message="Server destroyed",
    )


# ── Code update (git pull + rebuild) ─────────────────────────────────────────

_UPDATE_CMD = (
    "cd /opt/liftapp "
    "&& git fetch origin main "
    "&& git reset --hard origin/main "
    "&& docker compose up -d --build app "
    "&& echo '__DONE__'"
)

_SSH_OPTS = "-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes"


class BulkUpdateRequest(BaseModel):
    tenant_ids: list[uuid.UUID]


class UpdateStatus(BaseModel):
    tenant_id: uuid.UUID
    deploy_status: str
    last_deploy_at: Optional[datetime]
    deploy_output: Optional[str]


@router.post("/update", response_model=UpdateStatus)
def trigger_update(
    tenant_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Pull latest code and rebuild the app container on the tenant server."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.hetzner_server_ip:
        raise HTTPException(status_code=422, detail="Tenant has no server IP")
    if tenant.deploy_status == "UPDATING":
        raise HTTPException(status_code=409, detail="Update already in progress")

    tenant.deploy_status = "UPDATING"
    tenant.deploy_output = None
    db.commit()

    background_tasks.add_task(_do_update, tenant_id=tenant_id)

    return UpdateStatus(
        tenant_id=tenant_id,
        deploy_status="UPDATING",
        last_deploy_at=tenant.last_deploy_at,
        deploy_output=None,
    )


_bulk_update_router = APIRouter(prefix="/deploy", tags=["Deploy"])


@_bulk_update_router.post("/bulk-update")
def bulk_update(
    body: BulkUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Trigger code update for multiple tenants at once."""
    started = []
    skipped = []
    for tid in body.tenant_ids:
        tenant = db.get(Tenant, tid)
        if not tenant or not tenant.hetzner_server_ip:
            skipped.append(str(tid))
            continue
        if tenant.deploy_status == "UPDATING":
            skipped.append(str(tid))
            continue
        tenant.deploy_status = "UPDATING"
        tenant.deploy_output = None
        started.append(str(tid))
        background_tasks.add_task(_do_update, tenant_id=tid)
    db.commit()
    return {"started": started, "skipped": skipped}


# ── Background update task ────────────────────────────────────────────────────


def _do_update(tenant_id: uuid.UUID):
    """SSH into the tenant server, pull latest code, rebuild the app container."""
    import logging
    import subprocess
    from app.database import SessionLocal

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, tenant_id)
        if not tenant or not tenant.hetzner_server_ip:
            return

        ip = tenant.hetzner_server_ip
        logger.info("Starting code update for tenant %s at %s", tenant.slug, ip)

        result = subprocess.run(
            f"ssh {_SSH_OPTS} root@{ip} '{_UPDATE_CMD}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
        )

        output = (result.stdout + result.stderr).strip()
        # keep last 4 KB to avoid bloating the DB
        if len(output) > 4096:
            output = "...\n" + output[-4000:]

        success = result.returncode == 0 and "__DONE__" in result.stdout

        tenant.deploy_status = "SUCCESS" if success else "ERROR"
        tenant.last_deploy_at = datetime.now(timezone.utc)
        tenant.deploy_output = output
        db.commit()
        logger.info("Update %s for tenant %s", tenant.deploy_status, tenant.slug)

    except subprocess.TimeoutExpired:
        tenant = db.get(Tenant, tenant_id)
        if tenant:
            tenant.deploy_status = "ERROR"
            tenant.deploy_output = "Timeout — SSH command exceeded 10 minutes"
            tenant.last_deploy_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        logger.exception("Update failed for tenant %s: %s", tenant_id, exc)
        try:
            tenant = db.get(Tenant, tenant_id)
            if tenant:
                tenant.deploy_status = "ERROR"
                tenant.deploy_output = str(exc)
                tenant.last_deploy_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Background deploy task ────────────────────────────────────────────────────

def _do_deploy(tenant_id: uuid.UUID, body: DeployRequest):
    """Runs in a background thread — creates Hetzner server + waits for health."""
    import time
    import logging
    from app.database import SessionLocal
    from app.services.hetzner import create_tenant_server, wait_for_server_ip

    logger = logging.getLogger(__name__)
    db = SessionLocal()

    try:
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            return

        # 1. Create Hetzner server
        server_id = create_tenant_server(
            slug=tenant.slug,
            env_vars={
                "DATABASE_URL": f"postgresql://lift:{body.db_password}@localhost:5432/liftdb",
                "SECRET_KEY": body.secret_key,
                "CONTROL_PLANE_API_KEY": tenant.api_key,
                "ENVIRONMENT": "production",
                "GEMINI_API_KEY": body.gemini_api_key,
                "GMAIL_USER_CALLS": body.gmail_user_calls,
                "GMAIL_APP_PASSWORD_CALLS": body.gmail_app_password_calls,
                "GREENAPI_INSTANCE_ID": body.greenapi_instance_id,
                "GREENAPI_API_TOKEN": body.greenapi_api_token,
                "GOOGLE_MAPS_API_KEY": body.google_maps_api_key,
            },
        )
        tenant.hetzner_server_id = server_id
        db.commit()

        # 2. Wait for IP
        ip = wait_for_server_ip(server_id, timeout=180)
        tenant.hetzner_server_ip = ip
        tenant.api_url = f"https://{tenant.slug}.lift-agent.com"
        db.commit()

        # 3. Create DNS record (Cloudflare) slug.lift-agent.com → IP
        try:
            from app.services.cloudflare import create_dns_record
            create_dns_record(slug=tenant.slug, ip=ip)
            logger.info("DNS record created for %s → %s", tenant.slug, ip)
        except Exception as dns_err:
            logger.warning("DNS creation failed (non-fatal): %s", dns_err)

        # 4. Server is provisioning — monitor scheduler will poll every 5 min
        #    and promote DEPLOYING → ACTIVE once /health responds.
        logger.info("Tenant %s server provisioned at %s — monitor will promote to ACTIVE", tenant.slug, ip)

    except Exception as exc:
        logger.exception("Deploy failed for tenant %s: %s", tenant_id, exc)
        try:
            tenant = db.get(Tenant, tenant_id)
            if tenant:
                tenant.status = "ERROR"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
