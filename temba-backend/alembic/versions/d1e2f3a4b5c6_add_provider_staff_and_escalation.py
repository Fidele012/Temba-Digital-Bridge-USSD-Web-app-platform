"""add_provider_staff_and_escalation_level

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-06-03 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type using PL/pgSQL so the duplicate-object exception is
    # caught at the PostgreSQL level — avoids asyncpg checkfirst incompatibility.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE providerstaffrole AS ENUM ('supervisor', 'regional_manager', 'executive');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        'provider_staff',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'staff_role',
            PGEnum('supervisor', 'regional_manager', 'executive',
                   name='providerstaffrole', create_type=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_provider_staff_provider_id', 'provider_staff', ['provider_id'])
    op.create_index('ix_provider_staff_user_id', 'provider_staff', ['user_id'])

    # escalation_level: 0=none, 1=officer, 2=supervisor, 3=regional, 4=executive
    for table in ('reports', 'appointments', 'service_requests'):
        op.add_column(table, sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    for table in ('reports', 'appointments', 'service_requests'):
        op.drop_column(table, 'escalation_level')

    op.drop_index('ix_provider_staff_user_id', table_name='provider_staff')
    op.drop_index('ix_provider_staff_provider_id', table_name='provider_staff')
    op.drop_table('provider_staff')
    op.execute("DROP TYPE IF EXISTS providerstaffrole")
