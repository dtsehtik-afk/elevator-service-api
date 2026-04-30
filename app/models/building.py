"""Building model — a physical structure that may contain one or more elevators."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    elevators: Mapped[list["Elevator"]] = relationship(  # noqa: F821
        "Elevator", back_populates="building", foreign_keys="Elevator.building_id"
    )
    contacts: Mapped[list["Contact"]] = relationship(  # noqa: F821
        "Contact", back_populates="building", cascade="all, delete-orphan"
    )
    customer: Mapped[Optional["Customer"]] = relationship(  # noqa: F821
        "Customer", back_populates="buildings", foreign_keys="Building.customer_id"
    )
