"""Add missing uppercase enum values for reportstatus, servicerequeststatus, appointmentstatus

The initial schema created PostgreSQL enums with UPPERCASE values (OPEN, CLOSED, etc.)
because SQLAlchemy resolves Python enum members by their .name (uppercase) when building
native PG enum queries. The verification workflow migration incorrectly added lowercase
values (verified, closed_unverified) that SQLAlchemy never uses. This migration adds
the uppercase versions that SQLAlchemy expects.

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Uppercase values SQLAlchemy generates from Python enum .name — these were missing
# because the verification migration added lowercase instead
_REPORT_UPPERCASE = [
    'ACKNOWLEDGED', 'RESOLUTION_SUBMITTED', 'FOLLOW_UP_REQUIRED',
    'MANAGEMENT_REVIEW', 'VERIFIED', 'CLOSED_UNVERIFIED',
    'UNDER_REVIEW', 'IN_PROGRESS',  # belt-and-suspenders: already in initial but IF NOT EXISTS
]
_SR_UPPERCASE = [
    'ACKNOWLEDGED', 'RESOLUTION_SUBMITTED', 'FOLLOW_UP_REQUIRED',
    'MANAGEMENT_REVIEW', 'VERIFIED', 'CLOSED_UNVERIFIED',
    'IN_PROGRESS', 'PENDING', 'COMPLETED', 'CANCELLED', 'REJECTED',
]
_APPT_UPPERCASE = [
    'RESOLUTION_SUBMITTED', 'VERIFIED', 'CLOSED_UNVERIFIED',
    'PENDING', 'APPROVED', 'COMPLETED', 'CANCELLED', 'REJECTED', 'RESCHEDULED',
]


def upgrade() -> None:
    for v in _REPORT_UPPERCASE:
        op.execute(f"ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS '{v}'")
    for v in _SR_UPPERCASE:
        op.execute(f"ALTER TYPE servicerequeststatus ADD VALUE IF NOT EXISTS '{v}'")
    for v in _APPT_UPPERCASE:
        op.execute(f"ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS '{v}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op
    pass
