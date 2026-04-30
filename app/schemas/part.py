"""Pydantic schemas for parts (inventory) and part usage."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PartCreate(BaseModel):
    sku: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str = "יח'"
    quantity: int = 0
    min_quantity: int = 1
    cost_price: Optional[float] = None
    sell_price: Optional[float] = None
    supplier_name: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_email: Optional[str] = None
    notes: Optional[str] = None


class PartUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[int] = None
    min_quantity: Optional[int] = None
    cost_price: Optional[float] = None
    sell_price: Optional[float] = None
    supplier_name: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_email: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class PartResponse(BaseModel):
    id: uuid.UUID
    sku: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str
    quantity: int
    min_quantity: int
    cost_price: Optional[float] = None
    sell_price: Optional[float] = None
    supplier_name: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_email: Optional[str] = None
    is_active: bool
    is_low_stock: bool = False
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PartUsageCreate(BaseModel):
    part_id: uuid.UUID
    service_call_id: Optional[uuid.UUID] = None
    maintenance_id: Optional[uuid.UUID] = None
    technician_id: Optional[uuid.UUID] = None
    quantity: int = 1
    unit_price: Optional[float] = None
    notes: Optional[str] = None


class PartUsageResponse(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    part_name: Optional[str] = None
    service_call_id: Optional[uuid.UUID] = None
    maintenance_id: Optional[uuid.UUID] = None
    technician_id: Optional[uuid.UUID] = None
    quantity: int
    unit_price: Optional[float] = None
    notes: Optional[str] = None
    used_at: datetime
    model_config = {"from_attributes": True}
