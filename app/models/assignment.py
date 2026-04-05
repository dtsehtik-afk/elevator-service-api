"""Assignment model — links a service call to a technician."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Assignment(Base):
    """Records that a technician has been assigned to a service call."""

    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_call_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("service_calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technician_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("technicians.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # MANUAL | AUTO
    assignment_type: Mapped[str] = mapped_column(String(10), nullable=False, default="MANUAL")
    # PENDING_CONFIRMATION | CONFIRMED | REJECTED | CANCELLED | AUTO_ASSIGNED
    status: Mapped[str] = mapped_column(String(25), nullable=False, default="AUTO_ASSIGNED")
    # Travel time in minutes at time of assignment (from Google Maps)
    travel_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reminder_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    service_call: Mapped["ServiceCall"] = relationship(  # noqa: F821
        "ServiceCall", back_populates="assignments"
    )
    technician: Mapped["Technician"] = relationship(  # noqa: F821
        "Technician", back_populates="assignments"
    )


class AuditLog(Base):
    """Audit trail — every status change on a service call is recorded here."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_call_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("service_calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    changed_by: Mapped[str] = mapped_column(String(150), nullable=False)
    old_status: Mapped[str] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    service_call: Mapped["ServiceCall"] = relationship(  # noqa: F821
        "ServiceCall", back_populates="audit_logs"
    )
