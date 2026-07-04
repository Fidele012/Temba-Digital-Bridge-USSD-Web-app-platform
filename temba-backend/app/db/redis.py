"""Redis client — used for refresh token storage and rate limiting.

All helpers degrade gracefully when Redis is unavailable:
  - write operations (store/delete) become no-ops, a warning is logged
  - read operations return None
This means login always works; refresh/revocation requires Redis.
"""
import structlog
from redis.asyncio import Redis

from app.core.config import settings

log = structlog.get_logger(__name__)
_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None


# ── Token blacklist / refresh-token store ────────────────────────────────────

REFRESH_PREFIX = "rt:"
BLACKLIST_PREFIX = "bl:"


async def store_refresh_token(user_id: str, token: str, ttl_seconds: int) -> None:
    try:
        r = await get_redis()
        await r.setex(f"{REFRESH_PREFIX}{user_id}", ttl_seconds, token)
    except Exception:
        log.warning("redis_unavailable_store_refresh_token", user_id=user_id)


async def get_stored_refresh_token(user_id: str) -> str | None:
    try:
        r = await get_redis()
        return await r.get(f"{REFRESH_PREFIX}{user_id}")
    except Exception:
        log.warning("redis_unavailable_get_refresh_token", user_id=user_id)
        return None


async def delete_refresh_token(user_id: str) -> None:
    try:
        r = await get_redis()
        await r.delete(f"{REFRESH_PREFIX}{user_id}")
    except Exception:
        log.warning("redis_unavailable_delete_refresh_token", user_id=user_id)


async def blacklist_token(jti: str, ttl_seconds: int) -> None:
    try:
        r = await get_redis()
        await r.setex(f"{BLACKLIST_PREFIX}{jti}", ttl_seconds, "1")
    except Exception:
        log.warning("redis_unavailable_blacklist_token", jti=jti)


async def is_token_blacklisted(jti: str) -> bool:
    try:
        r = await get_redis()
        return await r.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
    except Exception:
        log.warning("redis_unavailable_is_blacklisted", jti=jti)
        return False


# ── Password-reset OTP store ──────────────────────────────────────────────────

OTP_PREFIX = "pwd_otp:"
OTP_TTL_SECONDS = 900  # 15 minutes


async def store_reset_otp(user_id: str, otp: str) -> None:
    try:
        r = await get_redis()
        await r.setex(f"{OTP_PREFIX}{user_id}", OTP_TTL_SECONDS, otp)
    except Exception:
        log.warning("redis_unavailable_store_otp", user_id=user_id)


async def get_reset_otp(user_id: str) -> str | None:
    try:
        r = await get_redis()
        return await r.get(f"{OTP_PREFIX}{user_id}")
    except Exception:
        log.warning("redis_unavailable_get_otp", user_id=user_id)
        return None


async def delete_reset_otp(user_id: str) -> None:
    try:
        r = await get_redis()
        await r.delete(f"{OTP_PREFIX}{user_id}")
    except Exception:
        log.warning("redis_unavailable_delete_otp", user_id=user_id)
