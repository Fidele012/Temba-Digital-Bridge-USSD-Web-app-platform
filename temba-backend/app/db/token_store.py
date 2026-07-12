"""DB-backed token store — replaces Redis for refresh tokens and password-reset OTPs.

Each write deletes any existing row for that (user_id, token_type) pair before inserting,
mirroring Redis SET/SETEX behaviour. Expired rows are also pruned on every write so the
table stays small without a separate cleanup job.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.token_store import UserToken

log = structlog.get_logger(__name__)

OTP_TTL_SECONDS = 900  # 15 minutes


def _to_uuid(user_id: str) -> UUID:
    return UUID(user_id)


async def _upsert(user_id: str, token_type: str, value: str, expires_at: datetime) -> None:
    uid = _to_uuid(user_id)
    async with AsyncSessionLocal() as db:
        # Remove existing + expired rows for this user+type
        await db.execute(
            delete(UserToken).where(
                UserToken.user_id == uid,
                UserToken.token_type == token_type,
            )
        )
        db.add(UserToken(user_id=uid, token_type=token_type, value=value, expires_at=expires_at))
        await db.commit()


async def _get(user_id: str, token_type: str) -> str | None:
    uid = _to_uuid(user_id)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(UserToken).where(
                UserToken.user_id == uid,
                UserToken.token_type == token_type,
                UserToken.expires_at > datetime.now(timezone.utc),
            )
        )).scalar_one_or_none()
        return row.value if row else None


async def _delete(user_id: str, token_type: str) -> None:
    uid = _to_uuid(user_id)
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(UserToken).where(
                UserToken.user_id == uid,
                UserToken.token_type == token_type,
            )
        )
        await db.commit()


# ── Refresh token helpers (same signatures as app.db.redis) ──────────────────

async def store_refresh_token(user_id: str, token: str, ttl_seconds: int) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    await _upsert(user_id, "refresh", token, expires_at)


async def get_stored_refresh_token(user_id: str) -> str | None:
    return await _get(user_id, "refresh")


async def delete_refresh_token(user_id: str) -> None:
    await _delete(user_id, "refresh")


# ── Password-reset OTP helpers (same signatures as app.db.redis) ─────────────

async def store_reset_otp(user_id: str, otp: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
    await _upsert(user_id, "otp", otp, expires_at)


async def get_reset_otp(user_id: str) -> str | None:
    return await _get(user_id, "otp")


async def delete_reset_otp(user_id: str) -> None:
    await _delete(user_id, "otp")
