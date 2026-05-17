"""Pydantic schemas for service call endpoints."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServiceCallCreate(BaseModel):
    """Schema for POST /calls."""
    elevator_id: uuid.UUID
    reported_by: str = Field(..., min_length=2, max_length=150)
    description: str = Field(..., min_length=5)
    priority: str = Field("MEDIUM", pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    fault_type: str = Field("OTHER", pattern="^(MECHANICAL|ELECTRICAL|SOFTWARE|STUCK|DOOR|RESCUE|MAINTENANCE|OTHER)$")
    # ERP
    caller_name: Optional[str] = None
    contact_phone_sms: Optional[str] = None
    contact_email: Optional[str] = None
    is_elevator_stopped: bool = False
    customer_rma: Optional[str] = None
    parent_call_id: Optional[uuid.UUID] = None


class ServiceCallUpdate(BaseModel):
    """Schema for PATCH /calls/{id} — all fields optional."""
    status: Optional[str] = Field(None, pattern="^(OPEN|ASSIGNED|IN_PROGRESS|RESOLVED|CLOSED|MONITORING)$")
    priority: Optional[str] = Field(None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    fault_type: Optional[str] = Field(None, pattern="^(MECHANICAL|ELECTRICAL|SOFTWARE|STUCK|DOOR|RESCUE|MAINTENANCE|OTHER)$")
    description: Optional[str] = Field(None, min_length=1)
    resolution_notes: Optional[str] = None
    quote_needed: Optional[bool] = None
    # ERP
    caller_name: Optional[str] = None
    contact_phone_sms: Optional[str] = None
    contact_email: Optional[str] = None
    is_elevator_stopped: Optional[bool] = None
    customer_rma: Optional[str] = None
    warranty_end_date: Optional[date] = None
    downtime_minutes: Optional[int] = None
    total_price: Optional[float] = None
    discount: Optional[float] = None
    station_count: Optional[int] = None
    parent_call_id: Optional[uuid.UUID] = None
    erp_metadata: Optional[Dict[str, Any]] = None


class ServiceCallResponse(BaseModel):
    """Full service call response."""
    id: uuid.UUID
    call_number: Optional[int] = None
    elevator_id: uuid.UUID
    reported_by: str
    description: str
    priority: str
    status: str
    fault_type: str
    is_recurring: bool
    resolution_notes: Optional[str]
    quote_needed: bool = False
    resolved_by: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    created_at: datetime
    assigned_at: Optional[datetime]
    resolved_at: Optional[datetime]
    # ERP
    caller_name: Optional[str] = None
    contact_phone_sms: Optional[str] = None
    contact_email: Optional[str] = None
    is_elevator_stopped: bool = False
    customer_rma: Optional[str] = None
    warranty_end_date: Optional[date] = None
    downtime_minutes: Optional[int] = None
    total_price: Optional[float] = None
    discount: Optional[float] = None
    station_count: Optional[int] = None
    parent_call_id: Optional[uuid.UUID] = None
    erp_metadata: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    """Audit log entry response."""
    id: uuid.UUID
    service_call_id: uuid.UUID
    changed_by: str
    old_status: Optional[str]
    new_status: str
    notes: Optional[str]
    changed_at: datetime

    model_config = {"from_attributes": True}


class AssignmentDetailResponse(BaseModel):
    """Assignment with technician name for detail view."""
    id: uuid.UUID
    technician_id: uuid.UUID
    technician_name: str
    assignment_type: str
    status: str
    travel_minutes: Optional[int]
    assigned_at: datetime

    model_config = {"from_attributes": True}


class CallDetailResponse(ServiceCallResponse):
    """Enriched service call response including elevator, assignments, and audit trail."""
    elevator_address: str
    elevator_city: str
    elevator_serial: Optional[str]
    assignments: List[AssignmentDetailResponse] = []
    audit_logs: List[AuditLogResponse] = []
