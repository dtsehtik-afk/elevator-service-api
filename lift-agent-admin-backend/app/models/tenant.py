import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, Integer, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid, JSON
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)    # e.g. https://client.lift-agent.com
    api_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)    # shared secret for /admin/* endpoints
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="BASIC")  # BASIC | PRO | ENTERPRISE
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Contact
    contact_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Billing
    monthly_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # ILS
    billing_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Cached stats (refreshed periodically)
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stats_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    modules: Mapped[list["TenantModule"]] = relationship("TenantModule", back_populates="tenant", cascade="all, delete-orphan")


class TenantModule(Base):
    __tablename__ = "tenant_modules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)   # WHATSAPP | AI_ASSIGN | INSPECTIONS | MAINTENANCE | MAP | IMPORT
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="modules")
