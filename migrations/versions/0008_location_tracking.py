"""Add last_location_at to technicians for location-reminder logic.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "technicians",
        sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("technicians", "last_location_at")
