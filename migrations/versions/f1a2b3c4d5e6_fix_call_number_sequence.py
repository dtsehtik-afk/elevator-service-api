"""Fix call_number sequence — create DB sequence and backfill missing numbers.

Revision ID: f1a2b3c4d5e6
Revises: e7e8b1599854
Create Date: 2026-05-13
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e7e8b1599854"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Create the sequence (if not already created from model's Sequence() obj)
    conn.execute(sa.text(
        "CREATE SEQUENCE IF NOT EXISTS service_calls_call_number_seq"
        " START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1"
    ))

    # 2. Backfill existing rows that have no call_number (NULL)
    conn.execute(sa.text("""
        UPDATE service_calls
        SET call_number = nextval('service_calls_call_number_seq')
        WHERE call_number IS NULL
        ORDER BY created_at ASC
    """))

    # 3. Attach sequence as the DEFAULT for the column going forward
    conn.execute(sa.text(
        "ALTER TABLE service_calls "
        "ALTER COLUMN call_number "
        "SET DEFAULT nextval('service_calls_call_number_seq')"
    ))

    # 4. Advance the sequence past the highest existing value to avoid conflicts
    conn.execute(sa.text(
        "SELECT setval('service_calls_call_number_seq', "
        "COALESCE((SELECT MAX(call_number) FROM service_calls), 0) + 1, false)"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE service_calls ALTER COLUMN call_number DROP DEFAULT"
    ))
    conn.execute(sa.text("DROP SEQUENCE IF EXISTS service_calls_call_number_seq"))
