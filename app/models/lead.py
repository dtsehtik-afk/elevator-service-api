"""Lead model — CRM ליד (לקוח פוטנציאלי)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # WEBSITE | PHONE | REFERRAL | EMAIL | SOCIAL | OTHER
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="OTHER")

    # NEW | CONTACTED | QUALIFIED | PROPOSAL | WON | LOST
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW", index=True)

    # Kanban column label (free text, e.g. "הצעת מחיר נשלחה")
    stage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # If lead converted to customer
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer: Mapped[Optional["Customer"]] = relationship(  # noqa: F821
        "Customer", back_populates="leads", foreign_keys=[customer_id]
    )
