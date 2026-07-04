"""add_provider_sla_and_contact_columns

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1e2d3c4b5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('providers', sa.Column('sla_response_hours', sa.Integer(), nullable=True))
    op.add_column('providers', sa.Column('sla_resolution_hours', sa.Integer(), nullable=True))
    op.add_column('providers', sa.Column('officer_name', sa.String(length=255), nullable=True))
    op.add_column('providers', sa.Column('officer_email', sa.String(length=255), nullable=True))
    op.add_column('providers', sa.Column('officer_phone', sa.String(length=20), nullable=True))
    op.add_column('providers', sa.Column('supervisor_name', sa.String(length=255), nullable=True))
    op.add_column('providers', sa.Column('supervisor_email', sa.String(length=255), nullable=True))
    op.add_column('providers', sa.Column('supervisor_phone', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('providers', 'supervisor_phone')
    op.drop_column('providers', 'supervisor_email')
    op.drop_column('providers', 'supervisor_name')
    op.drop_column('providers', 'officer_phone')
    op.drop_column('providers', 'officer_email')
    op.drop_column('providers', 'officer_name')
    op.drop_column('providers', 'sla_resolution_hours')
    op.drop_column('providers', 'sla_response_hours')
