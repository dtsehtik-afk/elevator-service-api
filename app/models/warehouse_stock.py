"""WarehouseStock model — current inventory balance per part per warehouse."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class WarehouseStock(Base):
    """
    Stores the current quantity of a given part in a given warehouse.
    This is the 'balance table' — updated atomically alongside every
    InventoryTransaction to avoid slow full-scan aggregations.

    CRITICAL: Never update `quantity` directly from application code.
    Always go through inventory_service.issue_part / transfer_part / receive_part,
    which update this table and create an InventoryTransaction in one DB transaction.
    """

    __tablename__ = "warehouse_stock"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    part_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Current balance — always >= 0
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Enforce one row per (part, warehouse) pair
    __table_args__ = (
        UniqueConstraint("part_id", "warehouse_id", name="uq_stock_part_warehouse"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])  # noqa: F821
    warehouse: Mapped["Warehouse"] = relationship(  # noqa: F821
        "Warehouse", back_populates="stock_items", foreign_keys=[warehouse_id]
    )
