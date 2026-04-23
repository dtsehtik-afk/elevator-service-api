import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from app.database import get_db
from app.models.tenant import Tenant, TenantModule
from app.auth.dependencies import get_current_admin

router = APIRouter(prefix="/tenants", tags=["tenants"])

VALID_MODULES = {"WHATSAPP", "AI_ASSIGN", "INSPECTIONS", "MAINTENANCE", "MAP", "IMPORT"}


class ModuleIn(BaseModel):
    module: str
    enabled: bool


class TenantCreate(BaseModel):
    name: str
    slug: str
    domain: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    plan: str = "BASIC"
    is_demo: bool = False
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    monthly_price: Optional[int] = None
    billing_notes: Optional[str] = None
    modules: list[ModuleIn] = []


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    is_demo: Optional[bool] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    monthly_price: Optional[int] = None
    billing_notes: Optional[str] = None


def _tenant_dict(t: Tenant) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "domain": t.domain,
        "api_url": t.api_url,
        "api_key": t.api_key,
        "plan": t.plan,
        "is_active": t.is_active,
        "is_demo": t.is_demo,
        "contact_name": t.contact_name,
        "contact_email": t.contact_email,
        "contact_phone": t.contact_phone,
        "monthly_price": t.monthly_price,
        "billing_notes": t.billing_notes,
        "stats": t.stats,
        "stats_refreshed_at": t.stats_refreshed_at.isoformat() if t.stats_refreshed_at else None,
        "last_seen_at": t.last_seen_at.isoformat() if t.last_seen_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "modules": [{"module": m.module, "enabled": m.enabled} for m in t.modules],
    }


@router.get("")
def list_tenants(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    tenants = db.query(Tenant).options(selectinload(Tenant.modules)).order_by(Tenant.name).all()
    return [_tenant_dict(t) for t in tenants]


@router.post("")
def create_tenant(body: TenantCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    if db.query(Tenant).filter(Tenant.slug == body.slug).first():
        raise HTTPException(status_code=409, detail="Slug already exists")
    tenant = Tenant(
        name=body.name, slug=body.slug, domain=body.domain, api_url=body.api_url, api_key=body.api_key,
        plan=body.plan, is_demo=body.is_demo, contact_name=body.contact_name,
        contact_email=body.contact_email, contact_phone=body.contact_phone,
        monthly_price=body.monthly_price, billing_notes=body.billing_notes,
    )
    db.add(tenant)
    db.flush()
    for m in body.modules:
        db.add(TenantModule(tenant_id=tenant.id, module=m.module, enabled=m.enabled))
    db.commit()
    db.refresh(tenant)
    return _tenant_dict(tenant)


@router.get("/{tenant_id}")
def get_tenant(tenant_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    t = db.query(Tenant).options(selectinload(Tenant.modules)).filter(Tenant.id == uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return _tenant_dict(t)


@router.patch("/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantUpdate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    t = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(t, field, val)
    db.commit()
    db.refresh(t)
    return _tenant_dict(t)


@router.delete("/{tenant_id}")
def delete_tenant(tenant_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    t = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.put("/{tenant_id}/modules")
def set_modules(tenant_id: str, modules: list[ModuleIn], db: Session = Depends(get_db), _=Depends(get_current_admin)):
    t = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(TenantModule).filter(TenantModule.tenant_id == t.id).delete()
    for m in modules:
        db.add(TenantModule(tenant_id=t.id, module=m.module, enabled=m.enabled))
    db.commit()
    return {"ok": True}
