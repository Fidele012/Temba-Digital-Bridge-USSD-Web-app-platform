"""Add resolution_deadline to reports/appointments/service_requests and expected_completion_date to reports

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # reports: resolution_deadline (timestamptz) + expected_completion_date (date)
    op.add_column("reports", sa.Column("resolution_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("expected_completion_date", sa.Date(), nullable=True))

    # appointments: resolution_deadline
    op.add_column("appointments", sa.Column("resolution_deadline", sa.DateTime(timezone=True), nullable=True))

    # service_requests: resolution_deadline
    op.add_column("service_requests", sa.Column("resolution_deadline", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("service_requests", "resolution_deadline")
    op.drop_column("appointments", "resolution_deadline")
    op.drop_column("reports", "expected_completion_date")
    op.drop_column("reports", "resolution_deadline")
