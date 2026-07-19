"""
Water quality endpoints — national readings set and maintained by WASAC only.

GET  /water-quality   → public, returns all 6 national readings
PUT  /water-quality   → WASAC-only, updates one or more readings
"""
import re
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_provider
from app.core.provider_utils import get_provider_for_user
from app.db.session import get_db
from app.models.user import User
from app.models.water_quality import WaterQualityReading
from app.schemas.water_quality import WaterQualityReadingPublic, WaterQualityUpdate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/water-quality", tags=["water-quality"])

_WASAC_RE = re.compile(r"wasac", re.IGNORECASE)

_DISPLAY_ORDER = ["ph", "turbidity", "chlorine", "ecoli", "hardness", "nitrate"]

_DEFAULT_READINGS = [
    {"parameter_key": "ph",        "label": "pH Level",       "value": "7.2",  "unit": "pH",        "status": "good"},
    {"parameter_key": "turbidity", "label": "Turbidity",      "value": "0.8",  "unit": "NTU",       "status": "good"},
    {"parameter_key": "chlorine",  "label": "Chlorine",       "value": "0.4",  "unit": "mg/L",      "status": "good"},
    {"parameter_key": "ecoli",     "label": "E. coli",        "value": "0",    "unit": "CFU/100ml", "status": "good"},
    {"parameter_key": "hardness",  "label": "Total Hardness", "value": "148",  "unit": "mg/L",      "status": "warn"},
    {"parameter_key": "nitrate",   "label": "Nitrate",        "value": "6.2",  "unit": "mg/L",      "status": "good"},
]


async def _ensure_seeded(db: AsyncSession) -> None:
    """Insert default rows on first deployment if the table is empty."""
    rows = (await db.execute(select(WaterQualityReading))).scalars().all()
    if not rows:
        for d in _DEFAULT_READINGS:
            db.add(WaterQualityReading(**d))
        await db.commit()


def _sorted(rows: list[WaterQualityReading]) -> list[WaterQualityReading]:
    order = {k: i for i, k in enumerate(_DISPLAY_ORDER)}
    return sorted(rows, key=lambda r: order.get(r.parameter_key, 99))


@router.get("", response_model=list[WaterQualityReadingPublic])
async def get_water_quality(db: Annotated[AsyncSession, Depends(get_db)]):
    """Public — any client may read the current national water quality readings."""
    await _ensure_seeded(db)
    rows = (await db.execute(select(WaterQualityReading))).scalars().all()
    return _sorted(rows)


@router.put("", response_model=list[WaterQualityReadingPublic])
async def update_water_quality(
    payload: WaterQualityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_provider)],
):
    """WASAC-only — updates one or more national water quality readings."""
    provider = await get_provider_for_user(current_user, db)
    if not provider or not _WASAC_RE.search(provider.organization_name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only WASAC (the national water authority) may update water quality readings.",
        )

    await _ensure_seeded(db)
    now = datetime.now(timezone.utc)

    for item in payload.readings:
        row = (
            await db.execute(
                select(WaterQualityReading).where(WaterQualityReading.parameter_key == item.parameter_key)
            )
        ).scalar_one_or_none()
        if row:
            row.value = item.value
            row.status = item.status
            row.updated_at = now
            row.updated_by_provider_id = provider.id

    await db.commit()
    rows = (await db.execute(select(WaterQualityReading))).scalars().all()
    log.info("Water quality updated by WASAC", provider_id=str(provider.id))
    return _sorted(rows)
