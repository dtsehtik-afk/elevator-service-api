"""AdminLog — structured event log for the Admin Console fault viewer."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database import Base


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
    source: Mapped[str] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
