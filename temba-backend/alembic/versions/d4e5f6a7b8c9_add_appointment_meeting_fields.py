"""Add appointment meeting enhancement fields

Revision ID: d4e5f6a7b8c9
Revises: c5d6e7f8a9b0
Create Date: 2026-07-22 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cancellation reason
    op.add_column("appointments", sa.Column("cancellation_reason", sa.Text(), nullable=True))

    # Dual-party post-appointment confirmation
    op.add_column("appointments", sa.Column("community_confirmed", sa.Boolean(), nullable=True))
    op.add_column("appointments", sa.Column("provider_confirmed", sa.Boolean(), nullable=True))
    op.add_column("appointments", sa.Column("conflict_flagged", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("appointments", sa.Column("auto_complete_at", sa.DateTime(timezone=True), nullable=True))

    # Post-confirmation outcome recording
    op.add_column("appointments", sa.Column("community_outcome", sa.String(20), nullable=True))
    op.add_column("appointments", sa.Column("provider_outcome_notes", sa.Text(), nullable=True))

    # 30-min reminder tracking
    op.add_column("appointments", sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("appointments", "reminder_sent")
    op.drop_column("appointments", "provider_outcome_notes")
    op.drop_column("appointments", "community_outcome")
    op.drop_column("appointments", "auto_complete_at")
    op.drop_column("appointments", "conflict_flagged")
    op.drop_column("appointments", "provider_confirmed")
    op.drop_column("appointments", "community_confirmed")
    op.drop_column("appointments", "cancellation_reason")
