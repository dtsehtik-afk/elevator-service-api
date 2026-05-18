"""Inventory router — ניהול מלאי חלקי חילוף + מחסנות."""

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.part import Part, PartUsage
from app.models.technician import Technician
from app.schemas.part import PartCreate, PartResponse, PartUpdate, PartUsageCreate, PartUsageResponse

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_PARTS_UPLOAD_DIR = "uploads/parts"

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ── Schemas ─────────────────────────────────────────────────────────────────────

class WarehouseResponse(BaseModel):
    id: str
    name: str
    warehouse_type: str
    is_active: bool
    address: Optional[str] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None

    model_config = {"from_attributes": True}


class WarehouseCreate(BaseModel):
    name: str
    warehouse_type: str = "MAIN"
    address: Optional[str] = None
    technician_id: Optional[uuid.UUID] = None


class WarehouseUpdate(BaseModel):
    name: Optional[str] = None
    warehouse_type: Optional[str] = None
    address: Optional[str] = None
    technician_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class StockItem(BaseModel):
    part_id: str
    part_name: str
    part_sku: Optional[str] = None
    category: Optional[str] = None
    quantity: int
    min_quantity: int
    is_low_stock: bool
    unit: str
    image_url: Optional[str] = None


class TransferRequest(BaseModel):
    part_id: uuid.UUID
    source_warehouse_id: uuid.UUID
    target_warehouse_id: uuid.UUID
    quantity: int
    notes: Optional[str] = None


class ReceiptRequest(BaseModel):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int
    unit_price: Optional[float] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class IssueRequest(BaseModel):
    part_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int
    service_call_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    transaction_type: str
    quantity: int
    unit_price: Optional[float] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    date: str
    part_name: Optional[str] = None
    source_warehouse_name: Optional[str] = None
    target_warehouse_name: Optional[str] = None


# ── Helper ───────────────────────────────────────────────────────────────────────

def _enrich_part(p: Part) -> PartResponse:
    r = PartResponse.model_validate(p)
    r.is_low_stock = p.quantity < p.min_quantity
    return r


def _get_or_create_stock(db: Session, part_id, warehouse_id):
    from app.models.warehouse_stock import WarehouseStock
    stock = db.query(WarehouseStock).filter(
        WarehouseStock.part_id == part_id,
        WarehouseStock.warehouse_id == warehouse_id,
    ).first()
    if not stock:
        stock = WarehouseStock(part_id=part_id, warehouse_id=warehouse_id, quantity=0)
        db.add(stock)
        db.flush()
    return stock


# ── Parts ────────────────────────────────────────────────────────────────────────

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


@router.post("/{part_id}/upload-image", response_model=PartResponse)
def upload_part_image(
    part_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Upload or replace the image for a part. Admin/Dispatcher/Warehouse-Manager only."""
    if current_user.role not in ("ADMIN", "DISPATCHER", "WAREHOUSE_MANAGER"):
        raise HTTPException(status_code=403, detail="רק מנהל מערכת או מנהל מחסן יכול להעלות תמונות")

    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")

    content_type = file.content_type or ""
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="קובץ חייב להיות תמונה (JPEG/PNG/WEBP/GIF)")

    ext = content_type.split("/")[-1].replace("jpeg", "jpg")
    os.makedirs(_PARTS_UPLOAD_DIR, exist_ok=True)
    filename = f"{part_id}.{ext}"
    filepath = os.path.join(_PARTS_UPLOAD_DIR, filename)

    data = file.file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="תמונה גדולה מדי — מקסימום 5MB")

    with open(filepath, "wb") as f:
        f.write(data)

    p.image_url = f"/uploads/parts/{filename}"
    db.commit()
    db.refresh(p)
    return _enrich_part(p)


@router.delete("/{part_id}/image", status_code=204)
def delete_part_image(
    part_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "DISPATCHER", "WAREHOUSE_MANAGER"):
        raise HTTPException(status_code=403, detail="אין הרשאה")
    p = db.query(Part).filter(Part.id == part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    if p.image_url:
        local = p.image_url.lstrip("/")
        if os.path.exists(local):
            os.remove(local)
    p.image_url = None
    db.commit()


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
    current_user: Technician = Depends(get_current_user),
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

    # Also deduct from the technician's vehicle warehouse if they have one
    try:
        from app.models.warehouse import Warehouse
        vehicle_wh = db.query(Warehouse).filter(
            Warehouse.technician_id == current_user.id,
            Warehouse.warehouse_type == "VEHICLE",
            Warehouse.is_active == True,
        ).first()
        if vehicle_wh:
            from app.models.warehouse_stock import WarehouseStock
            stock = db.query(WarehouseStock).filter_by(
                part_id=data.part_id, warehouse_id=vehicle_wh.id
            ).first()
            if stock and stock.quantity >= data.quantity:
                stock.quantity -= data.quantity
                from app.models.inventory_transaction import InventoryTransaction
                db.add(InventoryTransaction(
                    part_id=data.part_id,
                    source_warehouse_id=vehicle_wh.id,
                    transaction_type="ISSUE",
                    quantity=data.quantity,
                    unit_price=payload.get("unit_price"),
                    service_call_id=data.service_call_id,
                    created_by=current_user.id,
                    notes="שימוש בקריאת שירות",
                ))
    except Exception:
        pass

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


# ── Warehouses ────────────────────────────────────────────────────────────────

@router.get("/warehouses/list", response_model=List[WarehouseResponse])
def list_warehouses(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    from app.models.warehouse import Warehouse
    q = db.query(Warehouse)
    if not include_inactive:
        q = q.filter(Warehouse.is_active == True)
    warehouses = q.order_by(Warehouse.warehouse_type, Warehouse.name).all()
    result = []
    for w in warehouses:
        result.append(WarehouseResponse(
            id=str(w.id),
            name=w.name,
            warehouse_type=w.warehouse_type,
            is_active=w.is_active,
            address=w.address,
            technician_id=str(w.technician_id) if w.technician_id else None,
            technician_name=w.technician.name if w.technician else None,
        ))
    return result


@router.post("/warehouses", response_model=WarehouseResponse, status_code=201)
def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    from app.models.warehouse import Warehouse
    valid_types = {"MAIN", "VEHICLE", "LAB", "EXTERNAL"}
    if data.warehouse_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"warehouse_type must be one of {valid_types}")
    w = Warehouse(**data.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    return WarehouseResponse(
        id=str(w.id),
        name=w.name,
        warehouse_type=w.warehouse_type,
        is_active=w.is_active,
        address=w.address,
        technician_id=str(w.technician_id) if w.technician_id else None,
        technician_name=w.technician.name if w.technician else None,
    )


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
def update_warehouse(
    warehouse_id: uuid.UUID,
    data: WarehouseUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    from app.models.warehouse import Warehouse
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return WarehouseResponse(
        id=str(w.id),
        name=w.name,
        warehouse_type=w.warehouse_type,
        is_active=w.is_active,
        address=w.address,
        technician_id=str(w.technician_id) if w.technician_id else None,
        technician_name=w.technician.name if w.technician else None,
    )


@router.get("/warehouses/{warehouse_id}/stock", response_model=List[StockItem])
def get_warehouse_stock(
    warehouse_id: uuid.UUID,
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    low_stock_only: bool = Query(False),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    from app.models.warehouse import Warehouse
    from app.models.warehouse_stock import WarehouseStock
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    q = (
        db.query(WarehouseStock, Part)
        .join(Part, WarehouseStock.part_id == Part.id)
        .filter(WarehouseStock.warehouse_id == warehouse_id)
    )
    if search:
        q = q.filter(Part.name.ilike(f"%{search}%") | Part.sku.ilike(f"%{search}%"))
    if category:
        q = q.filter(Part.category == category)
    if low_stock_only:
        q = q.filter(WarehouseStock.quantity < Part.min_quantity)

    rows = q.order_by(Part.category, Part.name).all()
    return [
        StockItem(
            part_id=str(stock.part_id),
            part_name=part.name,
            part_sku=part.sku,
            category=part.category,
            quantity=stock.quantity,
            min_quantity=part.min_quantity,
            is_low_stock=stock.quantity < part.min_quantity,
            unit=part.unit,
            image_url=part.image_url,
        )
        for stock, part in rows
    ]


# ── Stock operations ──────────────────────────────────────────────────────────

@router.post("/stock/receive")
def receive_stock(
    data: ReceiptRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Receive parts into a warehouse (from supplier or external source)."""
    from app.models.warehouse import Warehouse
    from app.models.inventory_transaction import InventoryTransaction

    p = db.query(Part).filter(Part.id == data.part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")
    w = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    stock = _get_or_create_stock(db, data.part_id, data.warehouse_id)
    stock.quantity += data.quantity
    p.quantity += data.quantity

    tx = InventoryTransaction(
        part_id=data.part_id,
        target_warehouse_id=data.warehouse_id,
        transaction_type="RECEIPT",
        quantity=data.quantity,
        unit_price=data.unit_price,
        reference_number=data.reference_number,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(tx)
    db.commit()
    return {"status": "ok", "new_quantity": stock.quantity, "total_quantity": p.quantity}


@router.post("/stock/transfer")
def transfer_stock(
    data: TransferRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Transfer parts between warehouses."""
    from app.models.warehouse import Warehouse
    from app.models.warehouse_stock import WarehouseStock
    from app.models.inventory_transaction import InventoryTransaction

    if data.source_warehouse_id == data.target_warehouse_id:
        raise HTTPException(status_code=400, detail="Source and target must differ")
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    p = db.query(Part).filter(Part.id == data.part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")

    src_stock = db.query(WarehouseStock).filter(
        WarehouseStock.part_id == data.part_id,
        WarehouseStock.warehouse_id == data.source_warehouse_id,
    ).first()
    if not src_stock or src_stock.quantity < data.quantity:
        available = src_stock.quantity if src_stock else 0
        raise HTTPException(status_code=400, detail=f"Insufficient stock in source: {available} available")

    src_stock.quantity -= data.quantity
    tgt_stock = _get_or_create_stock(db, data.part_id, data.target_warehouse_id)
    tgt_stock.quantity += data.quantity

    tx = InventoryTransaction(
        part_id=data.part_id,
        source_warehouse_id=data.source_warehouse_id,
        target_warehouse_id=data.target_warehouse_id,
        transaction_type="TRANSFER",
        quantity=data.quantity,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(tx)
    db.commit()
    return {"status": "ok", "source_quantity": src_stock.quantity, "target_quantity": tgt_stock.quantity}


@router.post("/stock/issue")
def issue_stock(
    data: IssueRequest,
    db: Session = Depends(get_db),
    current_user: Technician = Depends(get_current_user),
):
    """Issue parts from a warehouse for a service call."""
    from app.models.warehouse import Warehouse
    from app.models.warehouse_stock import WarehouseStock
    from app.models.inventory_transaction import InventoryTransaction

    p = db.query(Part).filter(Part.id == data.part_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Part not found")

    src_stock = db.query(WarehouseStock).filter(
        WarehouseStock.part_id == data.part_id,
        WarehouseStock.warehouse_id == data.warehouse_id,
    ).first()
    if not src_stock or src_stock.quantity < data.quantity:
        available = src_stock.quantity if src_stock else 0
        raise HTTPException(status_code=400, detail=f"Insufficient stock: {available} available")

    src_stock.quantity -= data.quantity
    p.quantity = max(0, p.quantity - data.quantity)

    tx = InventoryTransaction(
        part_id=data.part_id,
        source_warehouse_id=data.warehouse_id,
        transaction_type="ISSUE",
        quantity=data.quantity,
        service_call_id=data.service_call_id,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(tx)
    db.commit()
    return {"status": "ok", "new_quantity": src_stock.quantity}


@router.get("/transactions", response_model=List[TransactionResponse])
def list_transactions(
    part_id: Optional[uuid.UUID] = Query(None),
    warehouse_id: Optional[uuid.UUID] = Query(None),
    transaction_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    from app.models.inventory_transaction import InventoryTransaction
    from app.models.warehouse import Warehouse

    q = db.query(InventoryTransaction)
    if part_id:
        q = q.filter(InventoryTransaction.part_id == part_id)
    if warehouse_id:
        q = q.filter(
            (InventoryTransaction.source_warehouse_id == warehouse_id) |
            (InventoryTransaction.target_warehouse_id == warehouse_id)
        )
    if transaction_type:
        q = q.filter(InventoryTransaction.transaction_type == transaction_type)
    txs = q.order_by(InventoryTransaction.date.desc()).limit(limit).all()

    result = []
    for tx in txs:
        result.append(TransactionResponse(
            id=str(tx.id),
            transaction_type=tx.transaction_type,
            quantity=tx.quantity,
            unit_price=float(tx.unit_price) if tx.unit_price else None,
            reference_number=tx.reference_number,
            notes=tx.notes,
            date=tx.date.isoformat(),
            part_name=tx.part.name if tx.part else None,
            source_warehouse_name=tx.source_warehouse.name if tx.source_warehouse else None,
            target_warehouse_name=tx.target_warehouse.name if tx.target_warehouse else None,
        ))
    return result
