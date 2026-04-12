"""Add caller_phones array to elevators for phone-based matching.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "elevators",
        sa.Column(
            "caller_phones",
            ARRAY(sa.String(30)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade():
    op.drop_column("elevators", "caller_phones")
