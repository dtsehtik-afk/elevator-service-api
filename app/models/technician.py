"""Technician model — represents a field technician."""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Technician(Base):
    """A field technician who handles service calls and maintenance."""

    __tablename__ = "technicians"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="TECHNICIAN")

    # Specializations stored as PostgreSQL array
    specializations: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)

    # WhatsApp number for notifications (may differ from phone)
    whatsapp_number: Mapped[str] = mapped_column(String(30), nullable=True)
    # Base / home location (used when live GPS is not yet shared)
    base_latitude: Mapped[float] = mapped_column(Float, nullable=True)
    base_longitude: Mapped[float] = mapped_column(Float, nullable=True)
    # Live GPS location (updated by technician's phone)
    current_latitude: Mapped[float] = mapped_column(Float, nullable=True)
    current_longitude: Mapped[float] = mapped_column(Float, nullable=True)

    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_daily_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

    # Preferred working area codes
    area_codes: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        "Assignment", back_populates="technician"
    )
    maintenance_schedules: Mapped[list["MaintenanceSchedule"]] = relationship(  # noqa: F821
        "MaintenanceSchedule", back_populates="technician"
    )
