"""1-click tenant deployment via Hetzner Cloud API."""

import uuid

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

        # 4. Wait for /health via nginx on port 80 (Docker takes ~2 min to start)
        health_url = f"http://{ip}/health"
        import httpx
        for _ in range(160):   # 160 × 15s = 40 minutes
            time.sleep(15)
            try:
                r = httpx.get(health_url, timeout=5)
                if r.status_code == 200:
                    tenant.status = "ACTIVE"
                    tenant.is_healthy = True
                    db.commit()
                    logger.info("Tenant %s deployed successfully at %s", tenant.slug, ip)
                    return
            except Exception:
                pass

        tenant.status = "ERROR"
        db.commit()
        logger.error("Tenant %s health check timed out", tenant.slug)

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
