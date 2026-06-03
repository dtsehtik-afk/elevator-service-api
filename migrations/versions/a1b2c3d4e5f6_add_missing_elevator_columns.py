"""Add missing elevator columns (responsible_technician, lead_source, secondary_customer,
maintenance_technician, consultant) that were dropped by erp_expansion or never migrated.

Also adds missing service_calls ERP extended fields.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    """Return True if the column already exists (safe to skip)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def upgrade() -> None:
    # ── elevators: restore columns removed by erp_expansion ──────────────────
    if not _col_exists('elevators', 'responsible_technician_id'):
        op.add_column('elevators', sa.Column(
            'responsible_technician_id', sa.Uuid(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_elevators_responsible_technician_id',
            'elevators', 'technicians',
            ['responsible_technician_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_elevators_responsible_technician_id',
            'elevators', ['responsible_technician_id'], unique=False,
        )

    if not _col_exists('elevators', 'lead_source'):
        op.add_column('elevators', sa.Column(
            'lead_source', sa.String(length=100), nullable=True,
        ))

    # ── elevators: new columns never migrated ─────────────────────────────────
    if not _col_exists('elevators', 'secondary_customer_id'):
        op.add_column('elevators', sa.Column(
            'secondary_customer_id', sa.Uuid(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_elevators_secondary_customer_id',
            'elevators', 'customers',
            ['secondary_customer_id'], ['id'],
            ondelete='SET NULL',
        )

    if not _col_exists('elevators', 'maintenance_technician_id'):
        op.add_column('elevators', sa.Column(
            'maintenance_technician_id', sa.Uuid(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_elevators_maintenance_technician_id',
            'elevators', 'technicians',
            ['maintenance_technician_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_elevators_maintenance_technician_id',
            'elevators', ['maintenance_technician_id'], unique=False,
        )

    if not _col_exists('elevators', 'consultant_id'):
        op.add_column('elevators', sa.Column(
            'consultant_id', sa.Uuid(), nullable=True,
        ))
        op.create_foreign_key(
            'fk_elevators_consultant_id',
            'elevators', 'consultants',
            ['consultant_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_elevators_consultant_id',
            'elevators', ['consultant_id'], unique=False,
        )

    if not _col_exists('elevators', 'notification_prefs'):
        op.add_column('elevators', sa.Column(
            'notification_prefs', sa.JSON(), nullable=True,
        ))

    # ── service_calls: ERP extended fields (safe re-add) ─────────────────────
    for col_name, col_def in [
        ('parent_call_id',         sa.Column('parent_call_id', sa.Uuid(), nullable=True)),
        ('warranty_end_date',      sa.Column('warranty_end_date', sa.Date(), nullable=True)),
        ('customer_rma',           sa.Column('customer_rma', sa.String(50), nullable=True)),
        ('caller_name',            sa.Column('caller_name', sa.String(150), nullable=True)),
        ('contact_phone_sms',      sa.Column('contact_phone_sms', sa.String(30), nullable=True)),
        ('contact_email',          sa.Column('contact_email', sa.String(100), nullable=True)),
        ('downtime_minutes',       sa.Column('downtime_minutes', sa.Integer(), nullable=True)),
        ('total_price',            sa.Column('total_price', sa.Numeric(12, 2), nullable=True)),
        ('discount',               sa.Column('discount', sa.Numeric(12, 2), nullable=True)),
        ('is_elevator_stopped',    sa.Column('is_elevator_stopped', sa.Boolean(), nullable=False, server_default='false')),
        ('station_count',          sa.Column('station_count', sa.Integer(), nullable=True)),
        ('erp_metadata',           sa.Column('erp_metadata', sa.JSON(), nullable=True)),
        ('resolved_by',            sa.Column('resolved_by', sa.String(150), nullable=True)),
    ]:
        if not _col_exists('service_calls', col_name):
            op.add_column('service_calls', col_def)

    # ── service_calls: add self-referential FK for parent_call_id ────────────
    conn = op.get_bind()
    fk_exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND tc.table_name = 'service_calls' "
        "  AND kcu.column_name = 'parent_call_id'"
    )).fetchone()
    if not fk_exists and _col_exists('service_calls', 'parent_call_id'):
        op.create_foreign_key(
            'fk_service_calls_parent_call_id',
            'service_calls', 'service_calls',
            ['parent_call_id'], ['id'],
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_service_calls_parent_call_id',
            'service_calls', ['parent_call_id'], unique=False,
        )


def downgrade() -> None:
    # Drop in reverse order — skip if column doesn't exist
    for col in ['erp_metadata', 'station_count', 'is_elevator_stopped',
                'discount', 'total_price', 'downtime_minutes',
                'contact_email', 'contact_phone_sms', 'caller_name',
                'customer_rma', 'warranty_end_date', 'resolved_by']:
        if _col_exists('service_calls', col):
            op.drop_column('service_calls', col)

    if _col_exists('service_calls', 'parent_call_id'):
        op.drop_constraint('fk_service_calls_parent_call_id', 'service_calls', type_='foreignkey')
        op.drop_index('ix_service_calls_parent_call_id', table_name='service_calls')
        op.drop_column('service_calls', 'parent_call_id')

    if _col_exists('elevators', 'notification_prefs'):
        op.drop_column('elevators', 'notification_prefs')

    if _col_exists('elevators', 'consultant_id'):
        op.drop_constraint('fk_elevators_consultant_id', 'elevators', type_='foreignkey')
        op.drop_index('ix_elevators_consultant_id', table_name='elevators')
        op.drop_column('elevators', 'consultant_id')

    if _col_exists('elevators', 'maintenance_technician_id'):
        op.drop_constraint('fk_elevators_maintenance_technician_id', 'elevators', type_='foreignkey')
        op.drop_index('ix_elevators_maintenance_technician_id', table_name='elevators')
        op.drop_column('elevators', 'maintenance_technician_id')

    if _col_exists('elevators', 'secondary_customer_id'):
        op.drop_constraint('fk_elevators_secondary_customer_id', 'elevators', type_='foreignkey')
        op.drop_column('elevators', 'secondary_customer_id')

    if _col_exists('elevators', 'lead_source'):
        op.drop_column('elevators', 'lead_source')

    if _col_exists('elevators', 'responsible_technician_id'):
        op.drop_constraint('fk_elevators_responsible_technician_id', 'elevators', type_='foreignkey')
        op.drop_index('ix_elevators_responsible_technician_id', table_name='elevators')
        op.drop_column('elevators', 'responsible_technician_id')
