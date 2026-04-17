"""Pydantic schemas for building endpoints."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ContactInBuilding(BaseModel):
    id: uuid.UUID
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: str
    auto_added: bool = False
    model_config = {"from_attributes": True}


class ElevatorInBuilding(BaseModel):
    id: uuid.UUID
    address: str
    city: str
    building_name: Optional[str] = None
    internal_number: Optional[str] = None
    status: str
    model_config = {"from_attributes": True}


class BuildingCreate(BaseModel):
    name: Optional[str] = None
    address: str
    city: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None


class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None


class BuildingResponse(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    address: str
    city: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    elevator_count: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}


class BuildingDetail(BuildingResponse):
    elevators: List[ElevatorInBuilding] = []
    contacts: List[ContactInBuilding] = []
