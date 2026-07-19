"""Add provider_id, announcement_type, and target to announcements

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-07-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("announcement_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("target", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_announcements_provider_id",
        "announcements",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_announcements_provider_id", "announcements", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_announcements_provider_id", table_name="announcements")
    op.drop_constraint("fk_announcements_provider_id", "announcements", type_="foreignkey")
    op.drop_column("announcements", "target")
    op.drop_column("announcements", "announcement_type")
    op.drop_column("announcements", "provider_id")
