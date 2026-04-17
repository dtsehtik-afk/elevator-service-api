"""Pydantic schemas for elevator endpoints."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ElevatorBase(BaseModel):
    address: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    building_name: Optional[str] = None
    floor_count: int = Field(1, ge=1, le=200)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE|UNDER_REPAIR)$")
    service_contract: Optional[str] = Field(None, pattern="^(ANNUAL_6|ANNUAL_12)$")


class ElevatorCreate(ElevatorBase):
    pass


class ElevatorUpdate(BaseModel):
    """All fields optional — PATCH semantics."""
    # Location
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    building_id: Optional[uuid.UUID] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Description
    building_name: Optional[str] = None
    notes: Optional[str] = None
    # Identity
    internal_number: Optional[str] = None
    labor_file_number: Optional[str] = None
    # Technical
    floor_count: Optional[int] = Field(None, ge=1, le=200)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    warranty_end: Optional[date] = None
    is_coded: Optional[bool] = None
    entry_code: Optional[str] = None
    # Contact
    contact_phone: Optional[str] = None
    intercom_phone: Optional[str] = None
    # Service
    service_type: Optional[str] = Field(None, pattern="^(REGULAR|COMPREHENSIVE)$")
    service_contract: Optional[str] = Field(None, pattern="^(ANNUAL_6|ANNUAL_12)$")
    maintenance_interval_days: Optional[int] = Field(None, ge=1)
    contract_start: Optional[date] = None
    contract_renewal: Optional[date] = None
    contract_end: Optional[date] = None
    drive_link: Optional[str] = None
    # Debt
    has_debt: Optional[bool] = None
    debt_freeze_date: Optional[date] = None
    # Maintenance
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    # Inspection
    last_inspection_date: Optional[date] = None
    next_inspection_date: Optional[date] = None
    inspector_name: Optional[str] = None
    inspector_phone: Optional[str] = None
    inspector_mobile: Optional[str] = None
    inspector_email: Optional[str] = None
    last_inspection_report_url: Optional[str] = None
    # Status
    status: Optional[str] = Field(None, pattern="^(ACTIVE|INACTIVE|UNDER_REPAIR)$")
    # Grouping
    management_company_id: Optional[uuid.UUID] = None


class ElevatorResponse(BaseModel):
    id: uuid.UUID
    # Identity
    internal_number: Optional[str] = None
    labor_file_number: Optional[str] = None
    # Location
    building_id: Optional[uuid.UUID] = None
    address: str
    city: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Description
    building_name: Optional[str] = None
    notes: Optional[str] = None
    # Technical
    floor_count: int
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    installation_date: Optional[date] = None
    serial_number: Optional[str] = None
    warranty_end: Optional[date] = None
    is_coded: bool = False
    entry_code: Optional[str] = None
    # Contact
    contact_phone: Optional[str] = None
    intercom_phone: Optional[str] = None
    caller_phones: List[str] = []
    # Service
    service_type: Optional[str] = None
    service_contract: Optional[str] = None
    maintenance_interval_days: Optional[int] = None
    contract_start: Optional[date] = None
    contract_renewal: Optional[date] = None
    contract_end: Optional[date] = None
    drive_link: Optional[str] = None
    # Debt
    has_debt: bool = False
    debt_freeze_date: Optional[date] = None
    # Maintenance
    last_service_date: Optional[date] = None
    next_service_date: Optional[date] = None
    # Inspection
    last_inspection_date: Optional[date] = None
    next_inspection_date: Optional[date] = None
    inspector_name: Optional[str] = None
    inspector_phone: Optional[str] = None
    inspector_mobile: Optional[str] = None
    inspector_email: Optional[str] = None
    last_inspection_report_url: Optional[str] = None
    # Status
    status: str
    risk_score: float
    # Grouping
    management_company_id: Optional[uuid.UUID] = None
    management_company_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ElevatorAnalytics(BaseModel):
    elevator_id: uuid.UUID
    total_calls: int
    recurring_calls: int
    calls_by_fault_type: dict
    calls_by_priority: dict
    avg_resolution_hours: Optional[float]
    risk_score: float
