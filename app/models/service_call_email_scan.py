"""Track processed service-call emails by Message-ID to avoid re-processing read emails."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceCallEmailScan(Base):
    __tablename__ = "service_call_email_scans"

    message_id: Mapped[str] = mapped_column(String(500), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
