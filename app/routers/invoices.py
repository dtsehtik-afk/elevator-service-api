"""Invoices + Receipts router — הנהלת חשבונות."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.invoice import Invoice, Receipt
from app.models.technician import Technician
from app.schemas.invoice import InvoiceCreate, InvoiceResponse, InvoiceUpdate, ReceiptCreate, ReceiptResponse

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _next_number(db: Session) -> str:
    year = date.today().year
    count = db.query(func.count(Invoice.id)).filter(
        func.extract("year", Invoice.created_at) == year
    ).scalar() or 0
    return f"INV-{year}-{count + 1:04d}"


def _enrich(inv: Invoice) -> InvoiceResponse:
    r = InvoiceResponse.model_validate(inv)
    r.customer_name = inv.customer.name if inv.customer else None
    r.balance = float(inv.total) - float(inv.amount_paid)
    return r


def _sync_status(inv: Invoice, db: Session):
    """Update invoice status based on payments."""
    paid = float(inv.amount_paid)
    total = float(inv.total)
    if paid >= total and total > 0:
        inv.status = "PAID"
        inv.paid_at = datetime.now(timezone.utc)
    elif paid > 0:
        inv.status = "PARTIAL"
    elif inv.due_date and inv.due_date < date.today() and inv.status not in ("PAID", "CANCELLED"):
        inv.status = "OVERDUE"


# ── Invoices ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[InvoiceResponse])
def list_invoices(
    customer_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    q = db.query(Invoice)
    if customer_id:
        q = q.filter(Invoice.customer_id == customer_id)
    if status:
        q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich(inv) for inv in invoices]


@router.post("", response_model=InvoiceResponse, status_code=201)
def create_invoice(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    payload = data.model_dump()
    payload["number"] = _next_number(db)
    inv = Invoice(**payload)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _enrich(inv)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _enrich(inv)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceUpdate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(inv, k, v)
    db.commit()
    db.refresh(inv)
    return _enrich(inv)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(inv)
    db.commit()


# ── Receipts ──────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/receipts", response_model=ReceiptResponse, status_code=201)
def add_receipt(
    invoice_id: uuid.UUID,
    data: ReceiptCreate,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    receipt = Receipt(**data.model_dump())
    db.add(receipt)
    db.flush()

    inv.amount_paid = float(inv.amount_paid) + data.amount
    _sync_status(inv, db)
    db.commit()
    db.refresh(receipt)
    return ReceiptResponse.model_validate(receipt)


@router.get("/{invoice_id}/receipts", response_model=List[ReceiptResponse])
def list_receipts(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return [ReceiptResponse.model_validate(r) for r in inv.receipts]


# ── Summary report ────────────────────────────────────────────────────────────

@router.get("/summary/debtors", tags=["Accounting"])
def debtors_summary(
    db: Session = Depends(get_db),
    _: Technician = Depends(get_current_user),
):
    """List customers with outstanding balances."""
    rows = db.query(
        Invoice.customer_id,
        func.sum(Invoice.total).label("total_billed"),
        func.sum(Invoice.amount_paid).label("total_paid"),
    ).filter(
        Invoice.status.in_(["SENT", "PARTIAL", "OVERDUE"])
    ).group_by(Invoice.customer_id).all()

    result = []
    for row in rows:
        customer = db.query(Customer).filter(Customer.id == row.customer_id).first()
        balance = float(row.total_billed or 0) - float(row.total_paid or 0)
        if balance > 0:
            result.append({
                "customer_id": str(row.customer_id),
                "customer_name": customer.name if customer else "—",
                "total_billed": float(row.total_billed or 0),
                "total_paid": float(row.total_paid or 0),
                "balance": balance,
            })
    result.sort(key=lambda x: x["balance"], reverse=True)
    return result
