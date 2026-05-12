"""InventoryTransaction model — immutable ledger of all inventory movements."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class InventoryTransaction(Base):
    """
    Every movement of a part is recorded here. Records are immutable — never
    update or delete them. To correct a mistake, create a reverse transaction.

    Transaction types:
      RECEIPT  — Goods received from a supplier into a warehouse.
      ISSUE    — Part dispensed from a warehouse for a service call.
      TRANSFER — Part moved between two warehouses (e.g. main → technician vehicle).
      RETURN   — Part returned from field back to a warehouse.
      ADJUST   — Manual stock adjustment (e.g. after physical count).

    quantity is ALWAYS positive. Direction is determined by transaction_type
    and the source/target warehouse fields.
    """

    __tablename__ = "inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── What moved ────────────────────────────────────────────────────────────
    part_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Where it moved ────────────────────────────────────────────────────────
    # source_warehouse_id: NULL for RECEIPT (comes from outside)
    source_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # target_warehouse_id: NULL for ISSUE (leaves the system)
    target_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Movement details ──────────────────────────────────────────────────────
    # RECEIPT | ISSUE | TRANSFER | RETURN | ADJUST
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Always positive — direction inferred from type + warehouses
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Price at time of transaction (for COGS / average cost calculation)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # ── Reference ─────────────────────────────────────────────────────────────
    # PO number, delivery note, or any external document ref
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    # Technician who performed the action
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )

    # ── Context links ─────────────────────────────────────────────────────────
    service_call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_calls.id", ondelete="SET NULL"), nullable=True, index=True
    )

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])  # noqa: F821
    source_warehouse: Mapped[Optional["Warehouse"]] = relationship(  # noqa: F821
        "Warehouse", foreign_keys=[source_warehouse_id]
    )
    target_warehouse: Mapped[Optional["Warehouse"]] = relationship(  # noqa: F821
        "Warehouse", foreign_keys=[target_warehouse_id]
    )
    created_by_technician: Mapped[Optional["Technician"]] = relationship(  # noqa: F821
        "Technician", foreign_keys=[created_by]
    )
    service_call: Mapped[Optional["ServiceCall"]] = relationship(  # noqa: F821
        "ServiceCall", foreign_keys=[service_call_id]
    )
