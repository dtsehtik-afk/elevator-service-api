"""IncomingCallLog — records every inbound webhook call, matched or not."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class IncomingCallLog(Base):
    """
    Audit table for every call received via the telephony-provider webhook.

    Every call is stored here regardless of whether a matching elevator was
    found, providing a complete call log for reports and manual review.
    """

    __tablename__ = "incoming_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Raw data ─────────────────────────────────────────────────────────────
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Parsed fields ────────────────────────────────────────────────────────
    caller_name:   Mapped[str] = mapped_column(String(200), nullable=True)
    caller_phone:  Mapped[str] = mapped_column(String(50),  nullable=True)
    call_city:     Mapped[str] = mapped_column(String(100), nullable=True)
    call_street:   Mapped[str] = mapped_column(String(200), nullable=True)
    call_type:     Mapped[str] = mapped_column(String(200), nullable=True)
    call_time_raw: Mapped[str] = mapped_column(String(50),  nullable=True)  # as reported in email
    fault_type:    Mapped[str] = mapped_column(String(20),  nullable=True)
    priority:      Mapped[str] = mapped_column(String(20),  nullable=True)

    # ── Match result ─────────────────────────────────────────────────────────
    # MATCHED | PARTIAL | UNMATCHED
    match_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNMATCHED", index=True)
    match_score:  Mapped[float] = mapped_column(Float, nullable=True)
    match_notes:  Mapped[str] = mapped_column(String(300), nullable=True)

    # ── Links to matched entities (nullable — may not have a match) ──────────
    elevator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("elevators.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    service_call_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("service_calls.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ── Relationships ────────────────────────────────────────────────────────
    elevator: Mapped["Elevator"] = relationship("Elevator")          # noqa: F821
    service_call: Mapped["ServiceCall"] = relationship("ServiceCall")  # noqa: F821
