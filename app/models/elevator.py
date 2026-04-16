"""Elevator model — represents a physical elevator unit."""

import json as _json
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import ARRAY, JSON, TypeDecorator, Uuid

from app.database import Base


class _FlexArray(TypeDecorator):
    """Stores as native ARRAY on PostgreSQL, JSON array on SQLite."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return []
        if dialect.name == "postgresql":
            return value
        return value if isinstance(value, list) else list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        try:
            return _json.loads(value)
        except (TypeError, ValueError):
            return []


class Elevator(Base):
    """Represents a single elevator managed by the service company."""

    __tablename__ = "elevators"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    building_name: Mapped[str] = mapped_column(String(255), nullable=True)
    floor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=True)
    installation_date: Mapped[date] = mapped_column(Date, nullable=True)
    serial_number: Mapped[str] = mapped_column(String(100), nullable=True, unique=True)
    contact_phone: Mapped[str] = mapped_column(String(30), nullable=True)
    last_service_date: Mapped[date] = mapped_column(Date, nullable=True)
    next_service_date: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", index=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Geocoded coordinates (lazily populated on first use)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    # Known caller phone numbers for this elevator (auto-populated from incoming calls)
    caller_phones: Mapped[list] = mapped_column(_FlexArray, nullable=False, default=list)
    # Service contract: how many maintenance treatments per year (6 or 12)
    # Values: "ANNUAL_6" | "ANNUAL_12" | None (unset — triggers warning in UI)
    service_contract: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    service_calls: Mapped[list["ServiceCall"]] = relationship(  # noqa: F821
        "ServiceCall", back_populates="elevator", cascade="all, delete-orphan"
    )
    maintenance_schedules: Mapped[list["MaintenanceSchedule"]] = relationship(  # noqa: F821
        "MaintenanceSchedule", back_populates="elevator", cascade="all, delete-orphan"
    )
