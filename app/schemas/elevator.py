"""Pydantic schemas for elevator endpoints."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ElevatorBase(BaseModel):
    """Shared fields for elevator create/update."""
    address: str = Field(..., min_length=5, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    building_name: Optional[str] = None
    floor_count: int = Field(..., ge=1, le=200)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE|UNDER_REPAIR)$")


class ElevatorCreate(ElevatorBase):
    """Schema for POST /elevators."""
    pass


class ElevatorUpdate(BaseModel):
    """Schema for PUT /elevators/{id} — all fields optional."""
    address: Optional[str] = Field(None, min_length=5, max_length=255)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    building_name: Optional[str] = None
    floor_count: Optional[int] = Field(None, ge=1, le=200)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(ACTIVE|INACTIVE|UNDER_REPAIR)$")


class ElevatorResponse(BaseModel):
    """Full elevator response — no strict validation, returns whatever is in DB."""
    id: uuid.UUID
    address: str
    city: str
    building_name: Optional[str] = None
    floor_count: int
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    status: str
    risk_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ElevatorAnalytics(BaseModel):
    """Analytics response for a specific elevator."""
    elevator_id: uuid.UUID
    total_calls: int
    recurring_calls: int
    calls_by_fault_type: dict
    calls_by_priority: dict
    avg_resolution_hours: Optional[float]
    risk_score: float
