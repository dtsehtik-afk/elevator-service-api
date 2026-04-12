"""Pydantic schemas for technician endpoints."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class TechnicianCreate(BaseModel):
    """Schema for creating a new technician account."""
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    password: str = Field(..., min_length=8)
    role: str = Field("TECHNICIAN", pattern="^(ADMIN|TECHNICIAN|DISPATCHER)$")
    specializations: List[str] = Field(default_factory=list)
    area_codes: List[str] = Field(default_factory=list)
    max_daily_calls: int = Field(8, ge=1, le=20)


class TechnicianUpdate(BaseModel):
    """Schema for updating a technician — all fields optional."""
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(ADMIN|TECHNICIAN|DISPATCHER)$")
    specializations: Optional[List[str]] = None
    area_codes: Optional[List[str]] = None
    max_daily_calls: Optional[int] = Field(None, ge=1, le=20)
    is_available: Optional[bool] = None
    is_on_call: Optional[bool] = None
    is_active: Optional[bool] = None
    base_latitude: Optional[float] = Field(None, ge=-90, le=90)
    base_longitude: Optional[float] = Field(None, ge=-180, le=180)


class LocationUpdate(BaseModel):
    """Schema for POST /technicians/location — real-time location update."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class TechnicianResponse(BaseModel):
    """Full technician response — password excluded."""
    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str]
    whatsapp_number: Optional[str]
    role: str
    specializations: List[str]
    current_latitude: Optional[float]
    current_longitude: Optional[float]
    last_location_at: Optional[datetime] = None
    base_latitude: Optional[float] = None
    base_longitude: Optional[float] = None
    is_available: bool
    is_on_call: bool = False
    is_active: bool
    max_daily_calls: int
    area_codes: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TechnicianStats(BaseModel):
    """Performance statistics for a technician."""
    technician_id: uuid.UUID
    total_calls_assigned: int
    total_calls_resolved: int
    avg_resolution_hours: Optional[float]
    calls_today: int
    calls_this_month: int
