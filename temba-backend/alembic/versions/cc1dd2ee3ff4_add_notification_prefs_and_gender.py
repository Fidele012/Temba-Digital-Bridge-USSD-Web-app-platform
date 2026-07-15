"""Add notification preferences and gender to users

Adds sms_notifications, email_notifications, in_app_alerts booleans and
a gender varchar column to the users table.

Revision ID: cc1dd2ee3ff4
Revises: e4f5a6b7c8d9
Create Date: 2026-07-15 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cc1dd2ee3ff4"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sms_notifications", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("in_app_alerts", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("gender", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "gender")
    op.drop_column("users", "in_app_alerts")
    op.drop_column("users", "email_notifications")
    op.drop_column("users", "sms_notifications")
