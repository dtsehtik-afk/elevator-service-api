"""Warehouse model — represents a storage location (main warehouse or technician vehicle)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Warehouse(Base):
    """
    Represents a physical storage location.
    Types:
      - MAIN: Central warehouse
      - VEHICLE: Technician's van/vehicle stock
      - EXTERNAL: External supplier or 3rd-party storage
    """

    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Identity ──────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "מחסן ראשי" or "רכב דניס"
    warehouse_type: Mapped[str] = mapped_column(String(50), nullable=False, default="MAIN")  # MAIN | VEHICLE | EXTERNAL
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Location ──────────────────────────────────────────────────────────────
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ── Ownership ─────────────────────────────────────────────────────────────
    # If warehouse_type = VEHICLE, this links to the responsible technician
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    technician: Mapped[Optional["Technician"]] = relationship(  # noqa: F821
        "Technician", foreign_keys=[technician_id]
    )
    stock_items: Mapped[list["WarehouseStock"]] = relationship(  # noqa: F821
        "WarehouseStock", back_populates="warehouse", cascade="all, delete-orphan"
    )
