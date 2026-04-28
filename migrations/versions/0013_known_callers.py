"""Add known_callers column to elevators table.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "elevators",
            sa.Column(
                "known_callers",
                ARRAY(sa.String),
                nullable=False,
                server_default="{}",
            ),
        )
    else:
        op.add_column(
            "elevators",
            sa.Column(
                "known_callers",
                sa.JSON,
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    op.drop_column("elevators", "known_callers")
