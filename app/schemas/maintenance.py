"""Pydantic schemas for maintenance schedule endpoints."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MaintenanceCreate(BaseModel):
    """Schema for scheduling a new maintenance event."""
    elevator_id: uuid.UUID
    technician_id: Optional[uuid.UUID] = None
    scheduled_date: date
    maintenance_type: str = Field(..., pattern="^(QUARTERLY|SEMI_ANNUAL|ANNUAL|INSPECTION)$")
    checklist: Optional[Dict[str, Any]] = Field(
        default=None,
        examples=[{"items": [{"name": "Lubricate cables", "done": False}]}],
    )


class MaintenanceUpdate(BaseModel):
    """Schema for updating a maintenance event — all fields optional."""
    technician_id: Optional[uuid.UUID] = None
    scheduled_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(SCHEDULED|COMPLETED|OVERDUE|CANCELLED)$")
    checklist: Optional[Dict[str, Any]] = None
    completion_notes: Optional[str] = None


class MaintenanceResponse(BaseModel):
    """Full maintenance schedule response."""
    id: uuid.UUID
    elevator_id: uuid.UUID
    technician_id: Optional[uuid.UUID]
    scheduled_date: date
    maintenance_type: str
    status: str
    checklist: Optional[Dict[str, Any]]
    completion_notes: Optional[str]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
