"""Edge case and boundary value tests — data validation and error handling."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_user
from app.models.user import UserRole


# ── Boundary Value Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_title_exact_min_length(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="minlen@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "other", "urgency": "low",
        "title": "ABCDE",
        "description": "A valid description for testing boundary",
    }, headers=auth_header(user))
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_report_title_one_below_min_rejected(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="belowmin@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "other", "urgency": "low",
        "title": "ABCD",
        "description": "A valid description for testing boundary",
    }, headers=auth_header(user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_report_with_coordinates_valid(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="coords@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "no_supply", "urgency": "high",
        "title": "No water in Gasabo area",
        "description": "Complete water outage since morning in the area",
        "latitude": -1.9403,
        "longitude": 29.8739,
        "province": "Kigali City", "district": "Gasabo",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["latitude"] == pytest.approx(-1.9403, abs=0.001)


@pytest.mark.asyncio
async def test_report_with_invalid_latitude_rejected(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="badlat@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "other", "urgency": "low",
        "title": "Invalid coords test report",
        "description": "Testing with latitude outside valid range",
        "latitude": 999.0,
        "longitude": 29.0,
    }, headers=auth_header(user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_report_invalid_category_rejected(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="badcat@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "nonexistent_category",
        "urgency": "low",
        "title": "Testing invalid category value",
        "description": "This category should not exist in the system",
    }, headers=auth_header(user))
    assert resp.status_code == 422


# ── Error Handling Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_nonexistent_report_returns_404(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="notfound@test.com")
    resp = await client.get(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000",
        headers=auth_header(user),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_nonexistent_endpoint_returns_404(client: AsyncClient):
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Different Data Value Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_all_categories(client: AsyncClient, db: AsyncSession):
    """Verify every valid category is accepted."""
    user = await make_user(db, email="allcats@test.com")
    categories = ["contamination", "pipe_burst", "low_pressure", "no_supply", "other"]
    for i, cat in enumerate(categories):
        resp = await client.post("/api/v1/reports", json={
            "category": cat, "urgency": "medium",
            "title": f"Test report for category {cat}",
            "description": f"Testing that {cat} category is accepted by the system",
        }, headers=auth_header(user))
        assert resp.status_code == 201, f"Category {cat} should be valid but got {resp.status_code}"


@pytest.mark.asyncio
async def test_report_all_urgency_levels(client: AsyncClient, db: AsyncSession):
    """Verify every valid urgency level is accepted."""
    user = await make_user(db, email="allurg@test.com")
    urgencies = ["low", "medium", "high", "critical"]
    for urg in urgencies:
        resp = await client.post("/api/v1/reports", json={
            "category": "other", "urgency": urg,
            "title": f"Test report urgency level {urg}",
            "description": f"Testing that {urg} urgency level works correctly",
        }, headers=auth_header(user))
        assert resp.status_code == 201, f"Urgency {urg} should be valid but got {resp.status_code}"


@pytest.mark.asyncio
async def test_register_with_rwandan_phone_number(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "rwphone@test.com",
        "password": "Test@12345",
        "full_name": "Rwandan Phone User",
        "role": "community",
        "phone": "+250788123456",
    })
    assert resp.status_code == 201
    assert resp.json()["phone"] == "+250788123456"


@pytest.mark.asyncio
async def test_register_with_kinyarwanda_name(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "kiny@test.com",
        "password": "Test@12345",
        "full_name": "Uwimana Jean Baptiste",
        "role": "community",
    })
    assert resp.status_code == 201
    assert resp.json()["full_name"] == "Uwimana Jean Baptiste"
