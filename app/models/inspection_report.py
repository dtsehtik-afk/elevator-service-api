"""InspectionReport model."""
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class InspectionReport(Base):
    __tablename__ = "inspection_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    elevator_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")  # "email" | "upload"
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="UNKNOWN")  # PASS | FAIL | UNKNOWN
    inspector_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    deficiency_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deficiencies: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    service_call_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
