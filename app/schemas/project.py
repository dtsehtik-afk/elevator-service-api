"""Pydantic schemas for the Projects module."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class ProjectTaskBase(BaseModel):
    name: str
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str = "PENDING"
    progress: int = 0
    notes: Optional[str] = None


class ProjectTaskCreate(ProjectTaskBase):
    pass


class ProjectTaskUpdate(BaseModel):
    name: Optional[str] = None
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    notes: Optional[str] = None


class ProjectTaskResponse(ProjectTaskBase):
    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    model_config = {"from_attributes": True}


class ProjectBase(BaseModel):
    name: str
    site: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    status: str = "PLANNING"
    project_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    elevator_count: Optional[int] = None
    manufacturer: Optional[str] = None
    contract_value: Optional[float] = None
    customer_id: Optional[uuid.UUID] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    consultant_id: Optional[uuid.UUID] = None
    responsible_technician_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    site: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None
    project_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    elevator_count: Optional[int] = None
    manufacturer: Optional[str] = None
    contract_value: Optional[float] = None
    customer_id: Optional[uuid.UUID] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    consultant_id: Optional[uuid.UUID] = None
    responsible_technician_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    customer_name: Optional[str] = None
    responsible_technician_name: Optional[str] = None
    consultant_name: Optional[str] = None
    consultant_phone: Optional[str] = None
    consultant_email: Optional[str] = None
    consultant_contacts: list = []
    model_config = {"from_attributes": True}


class ProjectDetail(ProjectResponse):
    tasks: List[ProjectTaskResponse] = []
