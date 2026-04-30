"""Pydantic schemas for leads (CRM)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LeadCreate(BaseModel):
    name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str = "OTHER"
    status: str = "NEW"
    stage: Optional[str] = None
    owner: Optional[str] = None
    estimated_value: Optional[float] = None
    customer_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None
    owner: Optional[str] = None
    estimated_value: Optional[float] = None
    customer_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str
    status: str
    stage: Optional[str] = None
    owner: Optional[str] = None
    estimated_value: Optional[float] = None
    customer_id: Optional[uuid.UUID] = None
    customer_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
