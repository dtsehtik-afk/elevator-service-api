"""Tenant CRUD — list, create, update, delete tenants."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_superadmin
from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter(prefix="/tenants", tags=["Tenants"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    name: str
    slug: str
    contact_email: str
    contact_phone: str | None = None
    plan: str = "TRIAL"
    notes: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    plan: str | None = None
    status: str | None = None
    api_url: str | None = None
    notes: str | None = None


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    contact_email: str
    contact_phone: str | None
    api_url: str | None
    api_key: str
    status: str
    plan: str
    billing_active: bool
    stripe_customer_id: str | None
    hetzner_server_id: int | None
    hetzner_server_ip: str | None
    modules: dict
    is_healthy: bool
    last_seen_at: datetime | None
    last_stats: dict | None
    created_at: datetime
    notes: str | None

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(
    body: TenantCreate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    if db.query(Tenant).filter_by(slug=body.slug).first():
        raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' already taken")
    tenant = Tenant(**body.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    db.delete(tenant)
    db.commit()


@router.post("/{tenant_id}/rotate-key", response_model=TenantOut)
def rotate_api_key(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_superadmin),
):
    """Generate a new API key for the tenant. Remember to update the env var on their server."""
    import secrets
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.api_key = secrets.token_urlsafe(32)
    db.commit()
    db.refresh(tenant)
    return tenant
