"""Tenant — one row per customer running a lift-agent instance."""

import secrets
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)  # used in subdomain
    contact_email: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(30), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    # Connectivity
    api_url: Mapped[str] = mapped_column(String(500), nullable=True)   # https://slug.lift-agent.com
    api_key: Mapped[str] = mapped_column(String(100), nullable=False, default=lambda: secrets.token_urlsafe(32))

    # Lifecycle
    # PENDING | DEPLOYING | ACTIVE | SUSPENDED | ERROR | CANCELLED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)

    # Plan & billing
    # TRIAL | BASIC | PRO | ENTERPRISE
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="TRIAL")
    stripe_customer_id: Mapped[str] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[str] = mapped_column(String(100), nullable=True)
    billing_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Hetzner infra
    hetzner_server_id: Mapped[int] = mapped_column(Integer, nullable=True)
    hetzner_server_ip: Mapped[str] = mapped_column(String(50), nullable=True)

    # Modules (cached copy — source of truth is on the tenant server)
    modules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Health
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stats: Mapped[dict] = mapped_column(JSONB, nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    snapshots: Mapped[list["TenantSnapshot"]] = relationship(  # noqa: F821
        "TenantSnapshot", back_populates="tenant", cascade="all, delete-orphan",
        order_by="TenantSnapshot.captured_at.desc()",
    )
