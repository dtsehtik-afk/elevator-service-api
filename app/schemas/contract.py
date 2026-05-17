"""Pydantic schemas for contracts."""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ContractCreate(BaseModel):
    customer_id: uuid.UUID
    contract_type: str = "SERVICE"
    status: str = "PENDING"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    monthly_price: Optional[float] = None
    total_value: Optional[float] = None
    payment_terms: int = 30
    auto_invoice: bool = False
    invoice_frequency: Optional[str] = None
    notes: Optional[str] = None
    elevator_ids: List[uuid.UUID] = []
    # ERP
    customer_type_ref: Optional[str] = None
    contact_person: Optional[str] = None
    paid_until: Optional[date] = None
    renewal_years: Optional[int] = None
    project_id: Optional[uuid.UUID] = None
    discount_percent: Optional[float] = None
    vat_percent: Optional[float] = None
    sales_rep_id: Optional[uuid.UUID] = None
    erp_metadata: Optional[Dict[str, Any]] = None


class ContractUpdate(BaseModel):
    contract_type: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    monthly_price: Optional[float] = None
    total_value: Optional[float] = None
    payment_terms: Optional[int] = None
    auto_invoice: Optional[bool] = None
    invoice_frequency: Optional[str] = None
    notes: Optional[str] = None
    elevator_ids: Optional[List[uuid.UUID]] = None
    # ERP
    customer_type_ref: Optional[str] = None
    contact_person: Optional[str] = None
    paid_until: Optional[date] = None
    renewal_years: Optional[int] = None
    project_id: Optional[uuid.UUID] = None
    discount_percent: Optional[float] = None
    vat_percent: Optional[float] = None
    sales_rep_id: Optional[uuid.UUID] = None
    erp_metadata: Optional[Dict[str, Any]] = None


class ContractResponse(BaseModel):
    id: uuid.UUID
    number: str
    customer_id: uuid.UUID
    customer_name: Optional[str] = None
    contract_type: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    monthly_price: Optional[float] = None
    total_value: Optional[float] = None
    payment_terms: int
    auto_invoice: bool
    invoice_frequency: Optional[str] = None
    last_invoiced_at: Optional[date] = None
    notes: Optional[str] = None
    elevator_count: int = 0
    # ERP
    customer_type_ref: Optional[str] = None
    contact_person: Optional[str] = None
    paid_until: Optional[date] = None
    renewal_years: Optional[int] = None
    project_id: Optional[uuid.UUID] = None
    discount_percent: Optional[float] = None
    vat_percent: Optional[float] = None
    sales_rep_id: Optional[uuid.UUID] = None
    sales_rep_name: Optional[str] = None
    erp_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
