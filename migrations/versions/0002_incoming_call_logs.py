"""Add incoming_call_logs table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incoming_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_text",      sa.Text,         nullable=False),
        sa.Column("caller_name",   sa.String(200),  nullable=True),
        sa.Column("caller_phone",  sa.String(50),   nullable=True),
        sa.Column("call_city",     sa.String(100),  nullable=True),
        sa.Column("call_street",   sa.String(200),  nullable=True),
        sa.Column("call_type",     sa.String(200),  nullable=True),
        sa.Column("call_time_raw", sa.String(50),   nullable=True),
        sa.Column("fault_type",    sa.String(20),   nullable=True),
        sa.Column("priority",      sa.String(20),   nullable=True),
        sa.Column("match_status",  sa.String(20),   nullable=False, server_default="UNMATCHED"),
        sa.Column("match_score",   sa.Float,        nullable=True),
        sa.Column("match_notes",   sa.String(300),  nullable=True),
        sa.Column(
            "elevator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elevators.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "service_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_calls.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_incoming_call_logs_match_status", "incoming_call_logs", ["match_status"])
    op.create_index("ix_incoming_call_logs_created_at",   "incoming_call_logs", ["created_at"])
    op.create_index("ix_incoming_call_logs_elevator_id",  "incoming_call_logs", ["elevator_id"])


def downgrade() -> None:
    op.drop_table("incoming_call_logs")
