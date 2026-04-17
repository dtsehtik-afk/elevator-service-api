"""Contact model — a person linked to a building (vaad, resident, management)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    building_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    management_company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("management_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    # VAAD / RESIDENT / MANAGEMENT / DIALER / OTHER
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # True if auto-populated from an incoming service call
    auto_added: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    building: Mapped[Optional["Building"]] = relationship(  # noqa: F821
        "Building", back_populates="contacts"
    )
    management_company: Mapped[Optional["ManagementCompany"]] = relationship(  # noqa: F821
        "ManagementCompany", back_populates="contacts"
    )
