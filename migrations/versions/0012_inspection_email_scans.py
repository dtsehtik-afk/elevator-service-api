"""Add inspection_email_scans table for tracking processed inspection emails.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_email_scans",
        sa.Column("message_id", sa.String(500), primary_key=True),
        sa.Column("gmail_uid", sa.String(50), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("sender", sa.String(200), nullable=True),
        sa.Column("attachment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reports_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("inspection_email_scans")
