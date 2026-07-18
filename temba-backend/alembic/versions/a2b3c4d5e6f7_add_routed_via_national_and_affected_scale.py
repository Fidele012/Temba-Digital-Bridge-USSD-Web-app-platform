"""Add routed_via_national_authority and affected_scale to reports

Revision ID: a2b3c4d5e6f7
Revises: cc1dd2ee3ff4
Create Date: 2026-07-18 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "cc1dd2ee3ff4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("routed_via_national_authority", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "reports",
        sa.Column("affected_scale", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "affected_scale")
    op.drop_column("reports", "routed_via_national_authority")
