"""Pydantic schemas for assignment endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ManualAssignRequest(BaseModel):
    """Request body for POST /calls/{id}/assign."""
    technician_id: uuid.UUID
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    """Assignment response."""
    id: uuid.UUID
    service_call_id: uuid.UUID
    technician_id: uuid.UUID
    assignment_type: str
    notes: Optional[str]
    assigned_at: datetime

    model_config = {"from_attributes": True}
