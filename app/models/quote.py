"""Quote model — הצעת מחיר."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Auto-generated number: Q-2026-0001
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    elevator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elevators.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Line items: [{"description": str, "quantity": float, "unit_price": float, "total": float}]
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=18.0)
    vat_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # DRAFT | SENT | ACCEPTED | REJECTED | EXPIRED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)

    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Filled when quote becomes a contract
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer", back_populates="quotes", foreign_keys=[customer_id]
    )
    elevator: Mapped[Optional["Elevator"]] = relationship(  # noqa: F821
        "Elevator", foreign_keys=[elevator_id]
    )
    contract: Mapped[Optional["Contract"]] = relationship(  # noqa: F821
        "Contract", foreign_keys=[contract_id], back_populates="quotes"
    )
