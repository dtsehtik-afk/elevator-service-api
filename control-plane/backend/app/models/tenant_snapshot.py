"""TenantSnapshot — health + stats poll result stored every 5 minutes."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class TenantSnapshot(Base):
    __tablename__ = "tenant_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=True)   # full /admin/stats payload
    error: Mapped[str] = mapped_column(JSONB, nullable=True)    # error message if unhealthy

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="snapshots")  # noqa: F821
