"""Add is_on_call column to technicians table.

Revision ID: 0006
Revises: 0005_assignment_reminder
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005_assignment_reminder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "technicians",
        sa.Column("is_on_call", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("technicians", "is_on_call")
