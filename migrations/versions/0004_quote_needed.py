"""Add quote_needed column to service_calls.

Revision ID: 0004_quote_needed
Revises: 0003_ai_assignment
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_quote_needed"
down_revision = "0003_ai_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_calls",
        sa.Column("quote_needed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("service_calls", "quote_needed")
