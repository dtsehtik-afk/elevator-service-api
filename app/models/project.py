"""Project and ProjectTask models for the Construction/Projects module."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from typing import Optional

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    site: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # PLANNING | ACTIVE | ON_HOLD | COMPLETED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNING")
    # NEW_INSTALLATION | RENOVATION | REPLACEMENT | MODERNIZATION
    project_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    elevator_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contract_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # Customer & contact
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_person: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Management & assignment
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL"), nullable=True
    )
    responsible_technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Installation milestones (manually checked) ────────────────────────────
    milestone_elevator_arrived:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_installation_started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_phase_a:              Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_phase_b:              Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_phase_c:              Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_initial_inspection:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    milestone_consultant_approved:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks: Mapped[list["ProjectTask"]] = relationship(
        "ProjectTask", back_populates="project", cascade="all, delete-orphan", order_by="ProjectTask.start_date"
    )
    customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[customer_id])
    responsible_technician: Mapped[Optional["Technician"]] = relationship("Technician", foreign_keys=[responsible_technician_id])
    consultant: Mapped[Optional["Consultant"]] = relationship("Consultant", foreign_keys=[consultant_id])


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    assignee: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # PENDING | IN_PROGRESS | DONE | BLOCKED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="tasks")

