"""SystemSettings — singleton row storing tenant-level feature flags."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Singleton key — always "default"
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, default="default")

    # Module flags: {"whatsapp": true, "email_calls": true, "google_drive": false, ...}
    modules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
