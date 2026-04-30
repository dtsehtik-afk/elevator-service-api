"""Customer model — CRM client with optional parent hierarchy (לקוח / לקוח אב)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # OWNER | MANAGEMENT_COMPANY | COMMITTEE | PRIVATE | CORPORATE
    customer_type: Mapped[str] = mapped_column(String(30), nullable=False, default="PRIVATE")

    # Self-referencing hierarchy: parent customer (לקוח אב)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Contact
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Financial
    vat_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    payment_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    credit_limit: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Self-referential relationships
    parent: Mapped[Optional["Customer"]] = relationship(
        "Customer", back_populates="children", remote_side="Customer.id", foreign_keys=[parent_id]
    )
    children: Mapped[list["Customer"]] = relationship(
        "Customer", back_populates="parent", foreign_keys=[parent_id]
    )

    # Downstream relationships
    buildings: Mapped[list["Building"]] = relationship(  # noqa: F821
        "Building", back_populates="customer", foreign_keys="Building.customer_id"
    )
    elevators: Mapped[list["Elevator"]] = relationship(  # noqa: F821
        "Elevator", back_populates="customer", foreign_keys="Elevator.customer_id"
    )
    quotes: Mapped[list["Quote"]] = relationship(  # noqa: F821
        "Quote", back_populates="customer", cascade="all, delete-orphan"
    )
    contracts: Mapped[list["Contract"]] = relationship(  # noqa: F821
        "Contract", back_populates="customer", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["Invoice"]] = relationship(  # noqa: F821
        "Invoice", back_populates="customer", cascade="all, delete-orphan"
    )
    leads: Mapped[list["Lead"]] = relationship(  # noqa: F821
        "Lead", back_populates="customer"
    )
