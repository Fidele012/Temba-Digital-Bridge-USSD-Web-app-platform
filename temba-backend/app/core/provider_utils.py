"""Shared helper: resolve the Provider for an authenticated user.

A user may be the primary account holder (Provider.user_id) or a staff
member linked via ProviderStaff.  All provider endpoints use this helper
so staff can access the same dashboard as the main account.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import Provider, ProviderStaff
from app.models.user import User


async def get_provider_for_user(user: User, db: AsyncSession) -> Provider | None:
    """Return the Provider associated with *user*, checking both the primary
    account and the ProviderStaff escalation table."""
    prov = (
        await db.execute(select(Provider).where(Provider.user_id == user.id))
    ).scalar_one_or_none()
    if prov:
        return prov

    # Select only provider_id to avoid the enum column mapping issue
    staff_provider_id = (
        await db.execute(
            select(ProviderStaff.provider_id).where(ProviderStaff.user_id == user.id)
        )
    ).scalar_one_or_none()
    if staff_provider_id:
        return (
            await db.execute(select(Provider).where(Provider.id == staff_provider_id))
        ).scalar_one_or_none()

    return None
