"""Security tests — authentication, authorization, and input validation."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_user
from app.models.user import UserRole


# ── Authentication Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_access_without_token_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_access_with_invalid_token_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_access_with_expired_token_format(client: AsyncClient):
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.invalid"},
    )
    assert resp.status_code in (401, 403)


# ── Authorization Tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_community_cannot_access_provider_endpoints(client: AsyncClient, db: AsyncSession):
    community = await make_user(db, email="comm_auth@test.com", role=UserRole.COMMUNITY)
    resp = await client.get("/api/v1/providers/me", headers=auth_header(community))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_report_owner_isolation(client: AsyncClient, db: AsyncSession):
    owner = await make_user(db, email="owner_sec@test.com")
    intruder = await make_user(db, email="intruder@test.com")

    create_resp = await client.post("/api/v1/reports", json={
        "category": "contamination", "urgency": "high",
        "title": "Water contamination alert",
        "description": "Water has unusual color and smell in my area",
        "province": "Kigali City", "district": "Kicukiro",
    }, headers=auth_header(owner))
    report_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/reports/{report_id}", headers=auth_header(intruder))
    assert resp.status_code == 403


# ── Input Validation Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_weak_password_rejected(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "weak@test.com",
        "password": "123",
        "full_name": "Weak Password User",
        "role": "community",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_rejected(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "not-an-email",
        "password": "Test@12345",
        "full_name": "Bad Email User",
        "role": "community",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_report_too_short_title_rejected(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="short_title@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst", "urgency": "medium",
        "title": "Hi",
        "description": "Valid description for the report issue",
    }, headers=auth_header(user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_report_empty_description_rejected(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="empty_desc@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst", "urgency": "medium",
        "title": "Valid Title Here",
        "description": "",
    }, headers=auth_header(user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_password_hash_not_exposed_in_response(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="nohash@test.com")
    resp = await client.get("/api/v1/users/me", headers=auth_header(user))
    data = resp.json()
    assert "hashed_password" not in data
    assert "password" not in data
    assert "ussd_pin_hash" not in data


@pytest.mark.asyncio
async def test_sql_injection_in_email_field(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@test.com'; DROP TABLE users; --",
        "password": "Test@12345",
        "full_name": "SQL Injection Test",
        "role": "community",
    })
    assert resp.status_code == 422
