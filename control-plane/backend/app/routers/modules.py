"""Module management — toggle feature flags on a tenant's server."""

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/tenants/{tenant_id}/modules", tags=["Modules"])

_TIMEOUT = 10.0


def _get_active_tenant(tenant_id: uuid.UUID, db: Session) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.api_url:
        raise HTTPException(status_code=409, detail="Tenant has no api_url configured")
    return tenant


class ModulesUpdate(BaseModel):
    modules: dict[str, bool]


class ModulesResponse(BaseModel):
    tenant_id: uuid.UUID
    modules: dict


@router.get("", response_model=ModulesResponse)
def get_modules(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Return cached module flags (no network call)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return ModulesResponse(tenant_id=tenant_id, modules=tenant.modules)


@router.post("", response_model=ModulesResponse)
def update_modules(
    tenant_id: uuid.UUID,
    body: ModulesUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Push module flag changes to the tenant server and cache the result."""
    tenant = _get_active_tenant(tenant_id, db)

    try:
        resp = httpx.post(
            f"{tenant.api_url.rstrip('/')}/admin/modules",
            json={"modules": body.modules},
            headers={"X-Control-Plane-Key": tenant.api_key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        updated_modules = resp.json().get("modules", {})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Tenant API error: {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach tenant: {e}")

    # Cache locally
    tenant.modules = {**tenant.modules, **updated_modules}
    db.commit()
    return ModulesResponse(tenant_id=tenant_id, modules=tenant.modules)


@router.post("/sync", response_model=ModulesResponse)
def sync_modules(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Pull current module state from the tenant server and update cache."""
    tenant = _get_active_tenant(tenant_id, db)

    try:
        resp = httpx.get(
            f"{tenant.api_url.rstrip('/')}/admin/modules",
            headers={"X-Control-Plane-Key": tenant.api_key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        tenant.modules = resp.json().get("modules", {})
        db.commit()
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach tenant: {e}")

    return ModulesResponse(tenant_id=tenant_id, modules=tenant.modules)
