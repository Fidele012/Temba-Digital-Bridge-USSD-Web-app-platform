"""Add sms_notifications, email_notifications, in_app_alerts to users

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-07-15 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sms_notifications", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("in_app_alerts", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("users", "in_app_alerts")
    op.drop_column("users", "email_notifications")
    op.drop_column("users", "sms_notifications")
