"""Add reminder_sent_at to assignments table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_assignment_reminder"
down_revision = "0004_quote_needed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignments", "reminder_sent_at")
