"""HR Record model — employee/HR data linked to a Technician."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class HRRecord(Base):
    """HR record for a technician — employment, salary, personal details."""

    __tablename__ = "hr_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    technician_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("technicians.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Employment
    employment_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    employment_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # FULL_TIME | PART_TIME | CONTRACT | FREELANCE
    employment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="FULL_TIME")

    # Salary
    # MONTHLY | HOURLY | PROJECT
    salary_type: Mapped[str] = mapped_column(String(20), nullable=False, default="MONTHLY")
    base_salary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hourly_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Personal
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emergency_contact: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    emergency_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    technician: Mapped["Technician"] = relationship(  # noqa: F821
        "Technician", back_populates="hr_record"
    )
