"""Part + PartUsage models — ניהול מלאי חלקי חילוף."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    sku: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="יח'")

    # Stock
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Pricing
    cost_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    sell_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # Supplier
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    supplier_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    supplier_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    usages: Mapped[list["PartUsage"]] = relationship(
        "PartUsage", back_populates="part", cascade="all, delete-orphan"
    )

    @property
    def is_low_stock(self) -> bool:
        return self.quantity < self.min_quantity


class PartUsage(Base):
    __tablename__ = "part_usage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    part_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_calls.id", ondelete="SET NULL"), nullable=True, index=True
    )
    maintenance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("maintenance_schedules.id", ondelete="SET NULL"), nullable=True
    )
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    part: Mapped["Part"] = relationship("Part", back_populates="usages")
    service_call: Mapped[Optional["ServiceCall"]] = relationship("ServiceCall")  # noqa: F821
    technician: Mapped[Optional["Technician"]] = relationship("Technician")  # noqa: F821
