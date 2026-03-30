"""Add coords to elevators, whatsapp + base-location to technicians, status to assignments

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Elevator — geocoded coordinates (filled lazily on first use)
    op.add_column("elevators", sa.Column("latitude",  sa.Float, nullable=True))
    op.add_column("elevators", sa.Column("longitude", sa.Float, nullable=True))

    # Technician — WhatsApp number + home/base coordinates
    op.add_column("technicians", sa.Column("whatsapp_number", sa.String(30),  nullable=True))
    op.add_column("technicians", sa.Column("base_latitude",   sa.Float,       nullable=True))
    op.add_column("technicians", sa.Column("base_longitude",  sa.Float,       nullable=True))

    # Assignment — confirmation status
    # PENDING_CONFIRMATION → CONFIRMED | REJECTED | CANCELLED | AUTO_ASSIGNED
    op.add_column(
        "assignments",
        sa.Column(
            "status",
            sa.String(25),
            nullable=False,
            server_default="AUTO_ASSIGNED",
        ),
    )
    # Estimated travel time in minutes (from Google Maps at time of assignment)
    op.add_column("assignments", sa.Column("travel_minutes", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("elevators", "latitude")
    op.drop_column("elevators", "longitude")
    op.drop_column("technicians", "whatsapp_number")
    op.drop_column("technicians", "base_latitude")
    op.drop_column("technicians", "base_longitude")
    op.drop_column("assignments", "status")
    op.drop_column("assignments", "travel_minutes")
