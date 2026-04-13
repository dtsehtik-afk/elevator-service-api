"""ServiceCall model — represents a single service request for an elevator."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class ServiceCall(Base):
    """A service call opened when an elevator requires attention."""

    __tablename__ = "service_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    elevator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("elevators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reported_by: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # CRITICAL | HIGH | MEDIUM | LOW
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    # OPEN | ASSIGNED | IN_PROGRESS | RESOLVED | CLOSED | MONITORING
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    # MECHANICAL | ELECTRICAL | SOFTWARE | STUCK | DOOR | OTHER
    fault_type: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER", index=True)

    # Automatically set True if the same fault_type recurred within 30 days
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    quote_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monitoring_notes: Mapped[str] = mapped_column(Text, nullable=True)
    monitoring_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    elevator: Mapped["Elevator"] = relationship(  # noqa: F821
        "Elevator", back_populates="service_calls"
    )
    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        "Assignment", back_populates="service_call", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog", back_populates="service_call", cascade="all, delete-orphan"
    )
