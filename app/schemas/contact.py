"""Pydantic schemas for contact endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str = Field("OTHER", pattern="^(VAAD|RESIDENT|MANAGEMENT|DIALER|OTHER)$")
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None
    auto_added: bool = False


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(VAAD|RESIDENT|MANAGEMENT|DIALER|OTHER)$")
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None
    auto_added: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}
