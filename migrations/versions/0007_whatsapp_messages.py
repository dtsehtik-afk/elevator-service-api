"""WhatsApp message conversation log.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-10
"""
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("msg_type", sa.String(30), nullable=False),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("transcription", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_whatsapp_messages_phone", "whatsapp_messages", ["phone"])
    op.create_index("ix_whatsapp_messages_timestamp", "whatsapp_messages", ["timestamp"])


def downgrade():
    op.drop_table("whatsapp_messages")
