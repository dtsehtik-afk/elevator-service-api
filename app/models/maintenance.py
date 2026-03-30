"""MaintenanceSchedule model — planned maintenance events for elevators."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class MaintenanceSchedule(Base):
    """A scheduled (or completed/overdue) maintenance event for an elevator."""

    __tablename__ = "maintenance_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    elevator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("elevators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technician_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("technicians.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # QUARTERLY | SEMI_ANNUAL | ANNUAL | INSPECTION
    maintenance_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # SCHEDULED | COMPLETED | OVERDUE | CANCELLED
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SCHEDULED", index=True
    )
    # JSON checklist: {"items": [{"name": "...", "done": false}, ...]}
    checklist: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)
    completion_notes: Mapped[str] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    elevator: Mapped["Elevator"] = relationship(  # noqa: F821
        "Elevator", back_populates="maintenance_schedules"
    )
    technician: Mapped["Technician"] = relationship(  # noqa: F821
        "Technician", back_populates="maintenance_schedules"
    )
