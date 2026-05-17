"""Pydantic schemas for customer endpoints."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CustomerBase(BaseModel):
    name: str
    customer_type: str = "PRIVATE"
    parent_id: Optional[uuid.UUID] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    contact_person: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: int = 30
    credit_limit: Optional[float] = None
    notes: Optional[str] = None
    is_active: bool = True
    # ERP
    creation_date: Optional[date] = None
    fax: Optional[str] = None
    industry_type: Optional[str] = None
    territory: Optional[str] = None
    delivery_route: Optional[str] = None
    website: Optional[str] = None
    sales_target: Optional[float] = None
    employee_count: Optional[int] = None
    erp_metadata: Optional[Dict[str, Any]] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    customer_type: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    contact_person: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[int] = None
    credit_limit: Optional[float] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    # ERP
    creation_date: Optional[date] = None
    fax: Optional[str] = None
    industry_type: Optional[str] = None
    territory: Optional[str] = None
    delivery_route: Optional[str] = None
    website: Optional[str] = None
    sales_target: Optional[float] = None
    employee_count: Optional[int] = None
    erp_metadata: Optional[Dict[str, Any]] = None


class CustomerRef(BaseModel):
    id: uuid.UUID
    name: str
    customer_type: str
    model_config = {"from_attributes": True}


class CustomerResponse(CustomerBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    parent_name: Optional[str] = None
    children_count: int = 0
    elevator_count: int = 0
    active_contracts: int = 0
    open_invoices: int = 0
    model_config = {"from_attributes": True}


class CustomerDetail(CustomerResponse):
    children: List[CustomerRef] = []
