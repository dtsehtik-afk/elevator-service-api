"""Pydantic schemas for activity log."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivityLogResponse(BaseModel):
    id: uuid.UUID
    actor_name: Optional[str] = None
    action: str
    message: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_ref: Optional[str] = None
    category: str
    created_at: datetime

    model_config = {"from_attributes": True}
