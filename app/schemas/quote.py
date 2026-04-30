"""Pydantic schemas for quotes."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QuoteItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float
    total: float


class QuoteCreate(BaseModel):
    customer_id: uuid.UUID
    elevator_id: Optional[uuid.UUID] = None
    items: List[Dict[str, Any]] = []
    subtotal: float = 0
    vat_rate: float = 18.0
    vat_amount: float = 0
    total: float = 0
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None


class QuoteUpdate(BaseModel):
    elevator_id: Optional[uuid.UUID] = None
    items: Optional[List[Dict[str, Any]]] = None
    subtotal: Optional[float] = None
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    total: Optional[float] = None
    status: Optional[str] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    contract_id: Optional[uuid.UUID] = None


class QuoteResponse(BaseModel):
    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    elevator_id: Optional[uuid.UUID] = None
    elevator_address: Optional[str] = None
    items: List[Dict[str, Any]] = []
    subtotal: float
    vat_rate: float
    vat_amount: float
    total: float
    status: str
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    contract_id: Optional[uuid.UUID] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
