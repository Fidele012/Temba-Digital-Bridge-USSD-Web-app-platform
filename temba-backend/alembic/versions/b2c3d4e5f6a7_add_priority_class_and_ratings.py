"""Add priority_class to reports and create ratings table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the priorityclass enum type (safe if already exists)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE priorityclass AS ENUM ('P1', 'P2', 'P3');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Add priority_class column to reports
    op.add_column(
        'reports',
        sa.Column(
            'priority_class',
            postgresql.ENUM('P1', 'P2', 'P3', name='priorityclass', create_type=False),
            nullable=True,
        ),
    )
    op.create_index('ix_reports_priority_class', 'reports', ['priority_class'])

    # Backfill priority_class for existing reports based on category + urgency
    op.execute("""
        UPDATE reports SET priority_class =
            CASE
                WHEN category = 'contamination' THEN 'P1'
                WHEN category = 'pipe_burst'  AND urgency IN ('high','critical') THEN 'P1'
                WHEN category = 'no_supply'   AND urgency = 'critical'           THEN 'P1'
                WHEN category = 'pipe_burst'  AND urgency = 'medium'             THEN 'P2'
                WHEN category = 'no_supply'   AND urgency IN ('high','medium')   THEN 'P2'
                WHEN category = 'low_pressure' AND urgency IN ('high','critical') THEN 'P2'
                WHEN category = 'water_quality' AND urgency = 'high'             THEN 'P2'
                ELSE 'P3'
            END
        WHERE priority_class IS NULL
    """)

    # Create ratings table (anonymous — no user_id by design)
    op.create_table(
        'ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('report_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('report_id', name='uq_ratings_report_id'),
    )
    op.create_index('ix_ratings_report_id', 'ratings', ['report_id'])
    op.create_index('ix_ratings_provider_id', 'ratings', ['provider_id'])


def downgrade() -> None:
    op.drop_index('ix_ratings_provider_id', table_name='ratings')
    op.drop_index('ix_ratings_report_id', table_name='ratings')
    op.drop_table('ratings')

    op.drop_index('ix_reports_priority_class', table_name='reports')
    op.drop_column('reports', 'priority_class')
    op.execute("DROP TYPE IF EXISTS priorityclass")
