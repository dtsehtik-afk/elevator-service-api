"""PartRequest model — tracks part replacement requests with approval workflow."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class PartRequest(Base):
    """
    Tracks a technician's request to use a part from inventory for a service call.

    Workflow:
      REGULAR service  → PENDING_APPROVAL (manager override required)
      COMPREHENSIVE    → PENDING_APPROVAL (service manager approval after contract check)
      Approved         → APPROVED → ISSUED (stock deducted)
      Faulty part must be returned before call can be CLOSED.
    """

    __tablename__ = "part_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Links ─────────────────────────────────────────────────────────────────
    service_call_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parts.id", ondelete="CASCADE"), nullable=False
    )
    source_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )

    # ── Request details ───────────────────────────────────────────────────────
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Workflow state ────────────────────────────────────────────────────────
    # PENDING_APPROVAL | APPROVED | REJECTED | ISSUED | CANCELLED
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_APPROVAL", index=True)
    # REGULAR_OVERRIDE (manager override for regular service)
    # COMPREHENSIVE_APPROVAL (service manager approval for comprehensive)
    approval_type: Mapped[str] = mapped_column(String(40), nullable=False, default="MANAGER_OVERRIDE")
    # REGULAR | COMPREHENSIVE — captured at request time
    service_type_snapshot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Faulty part return ────────────────────────────────────────────────────
    faulty_part_returned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    return_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    service_call: Mapped[Optional["ServiceCall"]] = relationship("ServiceCall", foreign_keys=[service_call_id])  # noqa: F821
    part: Mapped[Optional["Part"]] = relationship("Part", foreign_keys=[part_id])  # noqa: F821
    source_warehouse: Mapped[Optional["Warehouse"]] = relationship("Warehouse", foreign_keys=[source_warehouse_id])  # noqa: F821
    requester: Mapped[Optional["Technician"]] = relationship("Technician", foreign_keys=[requested_by])  # noqa: F821
    approver: Mapped[Optional["Technician"]] = relationship("Technician", foreign_keys=[approved_by])  # noqa: F821
