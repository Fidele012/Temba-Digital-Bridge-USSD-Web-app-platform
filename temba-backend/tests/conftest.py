"""
Pytest fixtures providing:
- An in-memory SQLite async engine (no Postgres needed for unit tests)
- A fake Redis (in-memory dict — no Redis server needed)
- A test client that overrides the DB dependency
- Factory helpers for users, providers, reports, appointments
"""
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Text, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.appointment import Appointment, AppointmentReason, AppointmentStatus, MeetingType
from app.models.provider import Provider, ProviderStatus
from app.models.report import Report, ReportCategory, ReportStatus, ReportUrgency
from app.models.user import User, UserRole


# ── SQLite adapter ───────────────────────────────────────────────────────────
# Replace PostgreSQL-only column types with TEXT so SQLite can create tables.

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_PG_ONLY_TYPES = {"ARRAY", "JSONB", "JSON"}

@event.listens_for(Base.metadata, "before_create")
def _patch_pg_types_for_sqlite(target, connection, **kw):
    if connection.dialect.name == "sqlite":
        for table in target.tables.values():
            for col in table.columns:
                visit = getattr(col.type, "__visit_name__", None)
                if visit in _PG_ONLY_TYPES:
                    col.type = Text()


# ── Fake Redis ───────────────────────────────────────────────────────────────
# Inject a dict-backed fake into app.db.redis._redis BEFORE any endpoint
# code calls get_redis().  Every redis function (store_refresh_token, etc.)
# internally does `r = await get_redis()` then `r.setex(...)` — so this
# single injection covers all of them without patching individual functions.

class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def aclose(self) -> None:
        pass

    def clear(self) -> None:
        self._store.clear()


_fake_redis = FakeRedis()

import app.db.redis as _redis_mod
_redis_mod._redis = _fake_redis

async def _noop_close() -> None:
    pass
_redis_mod.close_redis = _noop_close


# ── Notification mocks ───────────────────────────────────────────────────────
# send_email_background / send_sms_background are called as BackgroundTasks;
# the httpx ASGI transport awaits all background tasks before returning, so
# real SMTP/AT calls add latency and produce noisy errors in the test output.
# Patch both at the service module level AND at every endpoint module that
# imported the functions by direct name binding.

import app.services.notification_service as _notif_mod
import app.api.v1.endpoints.auth as _auth_mod
import app.api.v1.endpoints.providers as _providers_mod
import app.api.v1.endpoints.ussd as _ussd_mod

def _noop_send_email(*args, **kwargs) -> None:
    pass

def _noop_send_sms(*args, **kwargs) -> None:
    pass

_notif_mod.send_email_background = _noop_send_email
_notif_mod.send_sms_background = _noop_send_sms

_auth_mod.send_email_background = _noop_send_email
_auth_mod.send_sms_background = _noop_send_sms
_providers_mod.send_email_background = _noop_send_email
_ussd_mod.send_sms_background = _noop_send_sms


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def _clear_fake_redis():
    _fake_redis.clear()
    yield
    _fake_redis.clear()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── User factory ─────────────────────────────────────────────────────────────

async def make_user(
    db: AsyncSession,
    role: UserRole = UserRole.COMMUNITY,
    password: str = "Test@12345",
    **kwargs,
) -> User:
    defaults: dict[str, Any] = {
        "email": f"user_{role.value}_{id(kwargs)}@test.com",
        "hashed_password": hash_password(password),
        "full_name": f"Test {role.value.capitalize()}",
        "role": role,
        "is_active": True,
        "is_verified": True,
    }
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ── Provider factory ─────────────────────────────────────────────────────────

async def make_provider(db: AsyncSession, user: User, **kwargs) -> Provider:
    defaults: dict[str, Any] = {
        "user_id": user.id,
        "organization_name": "Test Water Co",
        "status": ProviderStatus.APPROVED,
        "service_categories": '["water_supply"]',
        "custom_services": '[]',
        "working_days": '["monday","tuesday","wednesday","thursday","friday"]',
        "max_appointments_per_day": 10,
        "unavailable_dates": '[]',
    }
    defaults.update(kwargs)
    provider = Provider(**defaults)
    db.add(provider)
    await db.flush()
    return provider
