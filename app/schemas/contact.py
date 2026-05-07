"""Pydantic schemas for contact endpoints."""

import uuid
from datetime import datetime
from typing import Optional, Dict

from pydantic import BaseModel, Field

ROLE_PATTERN = "^(VAAD|RESIDENT|MANAGEMENT|DIALER|CONSULTANT|OTHER)$"


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    role: str = Field("OTHER", pattern=ROLE_PATTERN)
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None
    elevator_id: Optional[uuid.UUID] = None
    notification_prefs: Optional[Dict[str, bool]] = None
    auto_added: bool = False


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = Field(None, pattern=ROLE_PATTERN)
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None
    elevator_id: Optional[uuid.UUID] = None
    notification_prefs: Optional[Dict[str, bool]] = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    landline: Optional[str] = None
    email: Optional[str] = None
    role: str
    notes: Optional[str] = None
    building_id: Optional[uuid.UUID] = None
    management_company_id: Optional[uuid.UUID] = None
    elevator_id: Optional[uuid.UUID] = None
    notification_prefs: Optional[Dict[str, bool]] = None
    auto_added: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}
