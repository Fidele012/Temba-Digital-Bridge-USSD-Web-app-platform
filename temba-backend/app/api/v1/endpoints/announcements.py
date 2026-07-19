"""
Announcement endpoints.

POST /announcements  → provider posts a new announcement (with optional location target)
GET  /announcements  → any logged-in user fetches announcements filtered by their location
"""
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_provider
from app.core.provider_utils import get_provider_for_user
from app.db.session import get_db
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import AnnouncementCreate, AnnouncementPublic

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/announcements", tags=["announcements"])


def _target_matches(target: dict | None, province: str | None, district: str | None,
                    sector: str | None, cell: str | None, village: str | None) -> bool:
    """Return True if this announcement's target includes the given location."""
    if not target:
        return True
    level = target.get("level", "national")
    if level == "national":
        return True
    provinces = target.get("provinces", [])
    districts = target.get("districts", [])
    sectors = target.get("sectors", [])
    cells = target.get("cells", [])
    villages = target.get("villages", [])
    if level == "province":
        return bool(province and province in provinces)
    if level == "district":
        return bool(province and province in provinces and district and district in districts)
    if level == "sector":
        return bool(province in provinces and district in districts and sector and sector in sectors)
    if level == "cell":
        return bool(province in provinces and district in districts and sector in sectors and cell and cell in cells)
    if level == "village":
        return bool(province in provinces and district in districts and sector in sectors and cell in cells and village and village in villages)
    return True


@router.post("", response_model=AnnouncementPublic, status_code=201)
async def create_announcement(
    payload: AnnouncementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_provider)],
):
    """Provider posts a new announcement visible to matching community members."""
    provider = await get_provider_for_user(current_user, db)
    now = datetime.now(timezone.utc)
    ann = Announcement(
        author_id=current_user.id,
        provider_id=provider.id if provider else None,
        title=payload.title,
        body=payload.body,
        announcement_type=payload.announcement_type,
        target=payload.target or {"level": "national"},
        is_published=True,
        published_at=now,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    log.info("Announcement created", ann_id=str(ann.id), provider=str(provider.id if provider else None))
    return ann


@router.get("", response_model=list[AnnouncementPublic])
async def list_announcements(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    province: Annotated[str | None, Query()] = None,
    district: Annotated[str | None, Query()] = None,
    sector: Annotated[str | None, Query()] = None,
    cell: Annotated[str | None, Query()] = None,
    village: Annotated[str | None, Query()] = None,
):
    """Return published announcements that match the caller's location."""
    q = (
        select(Announcement)
        .where(Announcement.is_published == True)  # noqa: E712
        .order_by(Announcement.published_at.desc())
        .limit(100)
    )
    rows = (await db.execute(q)).scalars().all()
    return [r for r in rows if _target_matches(r.target, province, district, sector, cell, village)]
