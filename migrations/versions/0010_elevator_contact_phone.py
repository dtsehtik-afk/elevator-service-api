"""Add contact_phone to elevators table.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "elevators",
        sa.Column("contact_phone", sa.String(30), nullable=True),
    )


def downgrade():
    op.drop_column("elevators", "contact_phone")
