"""ServiceCall model — represents a single service request for an elevator."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Sequence, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

_call_number_seq = Sequence("service_calls_call_number_seq", optional=True)

from app.database import Base


class ServiceCall(Base):
    """A service call opened when an elevator requires attention."""

    __tablename__ = "service_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_number: Mapped[Optional[int]] = mapped_column(
        Integer, _call_number_seq, nullable=True, unique=True, index=True,
    )
    elevator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("elevators.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reported_by: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # CRITICAL | HIGH | MEDIUM | LOW
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    # OPEN | ASSIGNED | IN_PROGRESS | RESOLVED | CLOSED | MONITORING
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    # MECHANICAL | ELECTRICAL | SOFTWARE | STUCK | DOOR | OTHER
    fault_type: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER", index=True)

    # Automatically set True if the same fault_type recurred within 30 days
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    quote_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_by: Mapped[str] = mapped_column(String(150), nullable=True)
    monitoring_notes: Mapped[str] = mapped_column(Text, nullable=True)
    monitoring_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # True when call arrived outside working hours and we're waiting for caller to approve surcharge
    after_hours_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # SLA deadline — computed at creation based on priority
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Commercial & Billing ────────────────────────────────────────────────
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #
    # ⚠️ הערה עסקית: ברירת מחדל FALSE מכוונת ונכונה!
    # רוב הקריאות מכוסות תחת חוזה השירות השוטף.
    # הקריאה תסומן כ-is_chargeable=True רק במקרים חריגים:
    #   - קריאה מחוץ לשעות עבודה (after_hours_pending=True)
    #   - ונדליזם
    #   - קריאה מיוחדת שלא קשורה לשירות השוטף
    # אל תשנה ברירת מחדל זו ללא אישור.
    is_chargeable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    # הזמנת רכש של הלקוח (דרוש לאישור חשבונית בחברות רבות)
    customer_po_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Time & SLA Tracking ────────────────────────────────────────────────
    technician_arrival_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    technician_departure_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    travel_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    work_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Backward compatibility flag: True only for calls created after BPM enforcement was deployed.
    # Existing calls get server_default=false so they are never blocked by the new validation.
    requires_time_report: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,           # Python ORM default for NEW calls
        server_default="false"  # SQL default for existing rows during migration
    )

    # ── Dictionaries & Signatures ──────────────────────────────────────────────
    malfunction_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # קוד תקלה קטלוגי
    repair_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # קוד תיקון קטלוגי
    contact_name_on_site: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # חותם בשטח
    customer_signature_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # לינק לחתימה דיגיטלית

    # ── ERP Extended Fields ──────────────────────────────────────────────────
    # Self-referential: this call is a follow-up to parent_call_id
    parent_call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_calls.id", ondelete="SET NULL"), nullable=True, index=True
    )
    warranty_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    customer_rma: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)    # מספר קריאה אצל הלקוח
    caller_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)    # שם המתקשר (מלבד reported_by)
    contact_phone_sms: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # טלפון לWA/SMS ישיר
    contact_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    downtime_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # זמן השבתת מכשיר
    total_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    discount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    is_elevator_stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    station_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # מס. תחנות
    erp_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    elevator: Mapped["Elevator"] = relationship(  # noqa: F821
        "Elevator", back_populates="service_calls"
    )
    parent_call: Mapped[Optional["ServiceCall"]] = relationship(
        "ServiceCall", foreign_keys=[parent_call_id], remote_side="ServiceCall.id"
    )
    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        "Assignment", back_populates="service_call", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog", back_populates="service_call", cascade="all, delete-orphan"
    )
