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
    status: str = "PLANNING"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    site: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    model_config = {"from_attributes": True}


class ProjectDetail(ProjectResponse):
    tasks: List[ProjectTaskResponse] = []
