"""Elevator model — represents a physical elevator unit."""

import json as _json
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import ARRAY, JSON, TypeDecorator, Uuid

from app.database import Base


class _FlexArray(TypeDecorator):
    """Stores as native ARRAY on PostgreSQL, JSON array on SQLite."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return []
        if dialect.name == "postgresql":
            return value
        return value if isinstance(value, list) else list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        try:
            return _json.loads(value)
        except (TypeError, ValueError):
            return []


class Elevator(Base):
    __tablename__ = "elevators"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Identity ─────────────────────────────────────────────────────────────
    # מס"ד — ID from the legacy system; used for cross-referencing on import
    internal_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)
    # מספר משרד העבודה — unique per elevator, extracted from inspection reports
    labor_file_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)

    # ── Location ──────────────────────────────────────────────────────────────
    building_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── Description ───────────────────────────────────────────────────────────
    # שם/תיאור — free-text nickname used by technicians
    building_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Technical specs ────────────────────────────────────────────────────────
    floor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    installation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    warranty_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # קודן — elevator has a key/code lock
    is_coded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entry_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ── Contact / phone ────────────────────────────────────────────────────────
    # Legacy single contact phone (kept for compatibility)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # חייגן — intercom/dialer phone number (manual update only)
    intercom_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Known caller phones (auto-populated from incoming calls)
    caller_phones: Mapped[list] = mapped_column(_FlexArray, nullable=False, default=list)
    # Known tenants/residents: [{"name": "...", "phone": "..."}] — auto-populated from calls
    known_callers: Mapped[list] = mapped_column(_FlexArray, nullable=False, default=list)

    # ── Service contract ──────────────────────────────────────────────────────
    # REGULAR / COMPREHENSIVE (רגיל / מקיף)
    service_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Legacy: ANNUAL_6 | ANNUAL_12 (kept for scheduler compatibility)
    service_contract: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Maintenance interval in days (30, 60, or custom) — kept for legacy reads
    maintenance_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Number of preventive maintenance visits per year: 2 | 4 | 6 | 12
    maintenance_times_per_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contract_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_renewal: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Link to Google Drive PDF (service contract document)
    drive_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Debt / freeze ─────────────────────────────────────────────────────────
    has_debt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    debt_freeze_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Maintenance dates ──────────────────────────────────────────────────────
    last_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Inspection ────────────────────────────────────────────────────────────
    last_inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # בודק מוסמך — certified inspector details
    inspector_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    inspector_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    inspector_mobile: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    inspector_email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_inspection_report_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Extended technical specs ──────────────────────────────────────────────
    motor_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    controller_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    door_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pit_depth_cm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    headroom_cm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    safety_certificate_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Status & Lifecycle ────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # בבניה | פעיל | מושבת | שיפוץ
    installation_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="פעיל")
    handover_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # תאריך מסירה ללקוח
    dismantle_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # תאריך פירוק

    # ── Deep Technical Specs ──────────────────────────────────────────────────
    engine_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # מס' סריאלי מנוע
    controller_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # מס' סריאלי פיקוד
    load_capacity_kg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # משקל נשיאה ק"ג
    max_persons: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # מספר נוסעים מקסימלי
    speed_m_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # מהירות מ/ש
    stops_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # מספר תחנות
    doors_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # מספר דלתות
    door_width_cm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # רוחב דלת ס"מ
    cabin_finish: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # גימור תא (נירוסטה/זכוכית/צבע)
    floor_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # סוג רצפה (שיש/גרניט/פח)

    # ── Compliance & IoT ──────────────────────────────────────────────────────
    accessibility_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # עומד בתקן נגישות
    fire_system_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # מחובר לגלאי אש
    generator_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # מחובר לגנרטור חרום
    iot_gateway_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # כתובת IP/MAC לבקרה חכמה

    # ── Grouping ──────────────────────────────────────────────────────────────
    management_company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("management_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # CRM customer link
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # טכנאי אחראי — responsible/assigned technician for this elevator
    responsible_technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # טכנאי אחראי תחזוקה — dedicated maintenance technician for this elevator
    maintenance_technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # יועץ — external consultant firm
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # לקוח אב נוסף — secondary customer entity linked to this elevator
    secondary_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # נכנסה מ — lead source / how the elevator was acquired
    lead_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # notification_prefs — who receives which automated notifications
    # e.g. {"customer": ["maintenance","inspection","invoice"], "secondary": ["inspection"]}
    notification_prefs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def management_company_name(self) -> Optional[str]:
        return self.management_company.name if self.management_company else None

    @property
    def responsible_technician_name(self) -> Optional[str]:
        return self.responsible_technician.name if self.responsible_technician else None

    @property
    def maintenance_technician_name(self) -> Optional[str]:
        return self.maintenance_technician.name if self.maintenance_technician else None

    @property
    def consultant_name(self) -> Optional[str]:
        return self.consultant.name if self.consultant else None

    @property
    def vaad_phone(self) -> Optional[str]:
        """Phone of the first VAAD (ועד בית) contact linked to this elevator."""
        for c in (self.contacts or []):
            if c.role == "VAAD" and c.phone:
                return c.phone
        return self.contact_phone  # fallback to legacy field

    @property
    def customer_name(self) -> Optional[str]:
        return self.customer.name if self.customer else None

    @property
    def customer_phone(self) -> Optional[str]:
        return self.customer.phone if self.customer else None

    @property
    def customer_email(self) -> Optional[str]:
        return self.customer.email if self.customer else None

    @property
    def customer_payment_terms_type(self) -> Optional[str]:
        return self.customer.payment_terms_type if self.customer else None

    @property
    def secondary_customer_name(self) -> Optional[str]:
        return self.secondary_customer.name if self.secondary_customer else None

    # ── Relationships ─────────────────────────────────────────────────────────
    building: Mapped[Optional["Building"]] = relationship(  # noqa: F821
        "Building", back_populates="elevators", foreign_keys=[building_id]
    )
    service_calls: Mapped[list["ServiceCall"]] = relationship(  # noqa: F821
        "ServiceCall", back_populates="elevator", cascade="all, delete-orphan"
    )
    maintenance_schedules: Mapped[list["MaintenanceSchedule"]] = relationship(  # noqa: F821
        "MaintenanceSchedule", back_populates="elevator", cascade="all, delete-orphan"
    )
    management_company: Mapped[Optional["ManagementCompany"]] = relationship(  # noqa: F821
        "ManagementCompany", back_populates="elevators", foreign_keys=[management_company_id]
    )
    customer: Mapped[Optional["Customer"]] = relationship(  # noqa: F821
        "Customer", back_populates="elevators", foreign_keys="Elevator.customer_id"
    )
    secondary_customer: Mapped[Optional["Customer"]] = relationship(  # noqa: F821
        "Customer", foreign_keys="Elevator.secondary_customer_id"
    )
    contacts: Mapped[list["Contact"]] = relationship(  # noqa: F821
        "Contact", back_populates="elevator", foreign_keys="Contact.elevator_id"
    )
    responsible_technician: Mapped[Optional["Technician"]] = relationship(  # noqa: F821
        "Technician", foreign_keys=[responsible_technician_id]
    )
    maintenance_technician: Mapped[Optional["Technician"]] = relationship(  # noqa: F821
        "Technician", foreign_keys=[maintenance_technician_id]
    )
    consultant: Mapped[Optional["Consultant"]] = relationship(  # noqa: F821
        "Consultant", back_populates="elevators", foreign_keys=[consultant_id]
    )
