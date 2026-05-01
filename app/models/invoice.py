"""Invoice + Receipt models — הנהלת חשבונות."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Auto-generated: INV-2026-0001
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Line items: [{"description": str, "quantity": float, "unit_price": float, "total": float}]
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=18.0)
    vat_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # DRAFT | SENT | PAID | PARTIAL | OVERDUE | CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)

    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="invoices", foreign_keys=[customer_id]
    )
    contract: Mapped[Optional["Contract"]] = relationship(  # noqa: F821
        "Contract", back_populates="invoices", foreign_keys=[contract_id]
    )
    receipts: Mapped[list["Receipt"]] = relationship(
        "Receipt", back_populates="invoice", cascade="all, delete-orphan"
    )


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # CASH | BANK_TRANSFER | CHECK | CREDIT_CARD | OTHER
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default="BANK_TRANSFER")
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="receipts")
