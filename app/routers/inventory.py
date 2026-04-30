"""Inventory router — ניהול מלאי חלקי חילוף."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.part import Part, PartUsage
from app.models.technician import Technician
from app.schemas.part import PartCreate, PartResponse, PartUpdate, PartUsageCreate, PartUsageResponse

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def _enrich_part(p: Part) -> PartResponse:
    r = PartResponse.model_validate(p)
    r.is_low_stock = p.quantity < p.min_quantity
    return r


@router.get("", response_model=List[PartResponse])
def list_parts(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    low_stock: bool = Query(False),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Part)
    if search:
        q = q.filter(Part.name.ilike(f"%{search}%") | Part.sku.ilike(f"%{search}%"))
    if category:
        q = q.filter(Part.category == category)
    if low_stock:
        q = q.filter(Part.quantity < Part.min_quantity)
    if is_active is not None:
        q = q.filter(Part.is_active == is_active)
    parts = q.order_by(Part.category, Part.name).offset(skip).limit(limit).all()
    return [_enrich_part(p) for p in parts]


@router.post("", response_model=PartResponse, status_code=201)
def create_part(
    data: PartCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = Part(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _enrich_part(p)


@router.get("/categories", response_model=List[str])
def list_categories(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    rows = db.query(Part.category).filter(Part.category.isnot(None)).distinct().all()
    return sorted([r[0] for r in rows if r[0]])


@router.get("/{part_id}", response_model=PartResponse)
def get_part(
    part_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    return _enrich_part(p)


@router.patch("/{part_id}", response_model=PartResponse)
def update_part(
    part_id: uuid.UUID,
    data: PartUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _enrich_part(p)


@router.patch("/{part_id}/adjust-stock")
def adjust_stock(
    part_id: uuid.UUID,
    delta: int = Query(..., description="Positive = add, negative = subtract"),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    new_qty = p.quantity + delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail="Stock cannot go below 0")
    p.quantity = new_qty
    db.commit()
    return {"part_id": str(p.id), "new_quantity": p.quantity, "is_low_stock": p.quantity < p.min_quantity}


@router.delete("/{part_id}", status_code=204)
def delete_part(
    part_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    db.delete(p)
    db.commit()


# ── Part usage ─────────────────────────────────────────────────────────────────

@router.post("/usage", response_model=PartUsageResponse, status_code=201)
def record_usage(
    data: PartUsageCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    p = db.query(Part).filter(Part.id == data.part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    if p.quantity < data.quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock: {p.quantity} available")

    payload = data.model_dump()
    if payload.get("unit_price") is None:
        payload["unit_price"] = float(p.sell_price) if p.sell_price else None

    usage = PartUsage(**payload)
    p.quantity -= data.quantity
    db.add(usage)
    db.commit()
    db.refresh(usage)

    r = PartUsageResponse.model_validate(usage)
    r.part_name = p.name
    return r


@router.get("/usage/by-call/{service_call_id}", response_model=List[PartUsageResponse])
def usage_by_call(
    service_call_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    usages = db.query(PartUsage).filter(PartUsage.service_call_id == service_call_id).all()
    result = []
    for u in usages:
        r = PartUsageResponse.model_validate(u)
        r.part_name = u.part.name if u.part else None
        result.append(r)
    return result
