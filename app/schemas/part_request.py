from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class PartRequestCreate(BaseModel):
    service_call_id: UUID
    part_id: UUID
    quantity: int = 1
    source_warehouse_id: Optional[UUID] = None
    notes: Optional[str] = None


class PartRequestApprove(BaseModel):
    approval_notes: Optional[str] = None


class PartRequestReject(BaseModel):
    rejection_reason: str


class PartRequestResponse(BaseModel):
    id: UUID
    service_call_id: UUID
    part_id: UUID
    source_warehouse_id: Optional[UUID]
    requested_by: Optional[UUID]
    approved_by: Optional[UUID]
    quantity: int
    notes: Optional[str]
    status: str
    approval_type: str
    service_type_snapshot: Optional[str]
    approval_notes: Optional[str]
    rejection_reason: Optional[str]
    approved_at: Optional[datetime]
    faulty_part_returned: bool
    return_warehouse_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    # Enriched
    part_name: Optional[str] = None
    part_sku: Optional[str] = None
    requester_name: Optional[str] = None
    approver_name: Optional[str] = None
    source_warehouse_name: Optional[str] = None

    model_config = {"from_attributes": True}
