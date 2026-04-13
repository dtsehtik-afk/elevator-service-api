"""Add monitoring_notes and monitoring_since to service_calls."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_calls", sa.Column("monitoring_notes", sa.Text(), nullable=True))
    op.add_column("service_calls", sa.Column("monitoring_since", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("service_calls", "monitoring_since")
    op.drop_column("service_calls", "monitoring_notes")
