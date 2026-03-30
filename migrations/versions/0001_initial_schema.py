"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- elevators ---
    op.create_table(
        "elevators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("building_name", sa.String(255)),
        sa.Column("floor_count", sa.Integer, nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("installation_date", sa.Date),
        sa.Column("serial_number", sa.String(100), unique=True),
        sa.Column("last_service_date", sa.Date),
        sa.Column("next_service_date", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("risk_score", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_elevators_city", "elevators", ["city"])
    op.create_index("ix_elevators_status", "elevators", ["status"])

    # --- technicians ---
    op.create_table(
        "technicians",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="TECHNICIAN"),
        sa.Column(
            "specializations",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("current_latitude", sa.Float),
        sa.Column("current_longitude", sa.Float),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_daily_calls", sa.Integer, nullable=False, server_default="8"),
        sa.Column(
            "area_codes",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_technicians_email", "technicians", ["email"])

    # --- service_calls ---
    op.create_table(
        "service_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "elevator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elevators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reported_by", sa.String(150), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("fault_type", sa.String(20), nullable=False, server_default="OTHER"),
        sa.Column("is_recurring", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolution_notes", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_service_calls_elevator_id", "service_calls", ["elevator_id"])
    op.create_index("ix_service_calls_priority", "service_calls", ["priority"])
    op.create_index("ix_service_calls_status", "service_calls", ["status"])
    op.create_index("ix_service_calls_fault_type", "service_calls", ["fault_type"])

    # --- assignments ---
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "technician_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("technicians.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assignment_type", sa.String(10), nullable=False, server_default="MANUAL"),
        sa.Column("notes", sa.Text),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_assignments_service_call_id", "assignments", ["service_call_id"])
    op.create_index("ix_assignments_technician_id", "assignments", ["technician_id"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.String(150), nullable=False),
        sa.Column("old_status", sa.String(20)),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_logs_service_call_id", "audit_logs", ["service_call_id"])

    # --- maintenance_schedules ---
    op.create_table(
        "maintenance_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "elevator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elevators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "technician_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("technicians.id", ondelete="SET NULL"),
        ),
        sa.Column("scheduled_date", sa.Date, nullable=False),
        sa.Column("maintenance_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SCHEDULED"),
        sa.Column("checklist", postgresql.JSONB),
        sa.Column("completion_notes", sa.Text),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_sent", sa.String(1), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_maintenance_elevator_id", "maintenance_schedules", ["elevator_id"]
    )
    op.create_index(
        "ix_maintenance_technician_id", "maintenance_schedules", ["technician_id"]
    )
    op.create_index(
        "ix_maintenance_scheduled_date", "maintenance_schedules", ["scheduled_date"]
    )
    op.create_index("ix_maintenance_status", "maintenance_schedules", ["status"])


def downgrade() -> None:
    op.drop_table("maintenance_schedules")
    op.drop_table("audit_logs")
    op.drop_table("assignments")
    op.drop_table("service_calls")
    op.drop_table("technicians")
    op.drop_table("elevators")
