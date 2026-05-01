"""Pydantic schemas for invoices and receipts."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    contract_id: Optional[uuid.UUID] = None
    items: List[Dict[str, Any]] = []
    subtotal: float = 0
    vat_rate: float = 18.0
    vat_amount: float = 0
    total: float = 0
    issue_date: date
    due_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    items: Optional[List[Dict[str, Any]]] = None
    subtotal: Optional[float] = None
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    total: Optional[float] = None
    status: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    contract_id: Optional[uuid.UUID] = None
    items: List[Dict[str, Any]] = []
    subtotal: float
    vat_rate: float
    vat_amount: float
    total: float
    amount_paid: float
    balance: float = 0
    status: str
    issue_date: date
    due_date: Optional[date] = None
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ReceiptCreate(BaseModel):
    invoice_id: uuid.UUID
    amount: float
    payment_method: str = "BANK_TRANSFER"
    reference: Optional[str] = None
    payment_date: date
    notes: Optional[str] = None


class ReceiptResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: float
    payment_method: str
    reference: Optional[str] = None
    payment_date: date
    notes: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}
