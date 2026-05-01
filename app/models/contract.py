"""Contract model — חוזה שירות / תחזוקה."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Auto-generated: C-2026-0001
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # SERVICE | MAINTENANCE | INSPECTION | RENOVATION | OTHER
    contract_type: Mapped[str] = mapped_column(String(30), nullable=False, default="SERVICE")

    # PENDING | ACTIVE | EXPIRED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    monthly_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    total_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    payment_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Billing: auto-create invoices
    auto_invoice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # MONTHLY | QUARTERLY | ANNUAL
    invoice_frequency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_invoiced_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="contracts", foreign_keys=[customer_id]
    )
    quotes: Mapped[list["Quote"]] = relationship(  # noqa: F821
        "Quote", back_populates="contract", foreign_keys="Quote.contract_id"
    )
    invoices: Mapped[list["Invoice"]] = relationship(  # noqa: F821
        "Invoice", back_populates="contract", foreign_keys="Invoice.contract_id"
    )
    elevator_contracts: Mapped[list["ElevatorContract"]] = relationship(
        "ElevatorContract", back_populates="contract", cascade="all, delete-orphan"
    )


class ElevatorContract(Base):
    """Many-to-many: elevators ↔ contracts."""
    __tablename__ = "elevator_contracts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    elevator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elevators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="elevator_contracts")
    elevator: Mapped["Elevator"] = relationship("Elevator")  # noqa: F821
