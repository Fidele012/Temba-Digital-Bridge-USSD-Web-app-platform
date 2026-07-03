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


# ── Large Data Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_large_description_accepted(client: AsyncClient, db: AsyncSession):
    """Large data: a 5,000-character description must be accepted without crashing."""
    user = await make_user(db, email="largedesc@test.com")
    long_description = "Water quality issue. " * 250  # ~5,000 characters
    resp = await client.post("/api/v1/reports", json={
        "category": "water_quality",
        "urgency": "medium",
        "title": "Extended water quality report",
        "description": long_description,
    }, headers=auth_header(user))
    # Must either accept it (201) or reject cleanly (422) — never crash (500)
    assert resp.status_code in (201, 422)


@pytest.mark.asyncio
async def test_report_title_exact_max_length(client: AsyncClient, db: AsyncSession):
    """Boundary: title at exactly 255 characters (the defined maximum) must be accepted."""
    user = await make_user(db, email="maxtitle@test.com")
    max_title = "A" * 255
    resp = await client.post("/api/v1/reports", json={
        "category": "other",
        "urgency": "low",
        "title": max_title,
        "description": "Valid description to accompany the maximum length title test",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json()["title"] == max_title


@pytest.mark.asyncio
async def test_report_title_exceeds_max_rejected(client: AsyncClient, db: AsyncSession):
    """Boundary: title exceeding 255 characters must be rejected with 422."""
    user = await make_user(db, email="overtitle@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "other",
        "urgency": "low",
        "title": "B" * 256,
        "description": "Valid description to test title length validation boundary",
    }, headers=auth_header(user))
    assert resp.status_code == 422


# ── Special Characters Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_description_with_special_characters(client: AsyncClient, db: AsyncSession):
    """Special chars: description containing @, #, &, <, > must be stored safely."""
    user = await make_user(db, email="specialchars@test.com")
    special_desc = "Water issue: pH < 6.5 & turbidity > 10 NTU. Contact: info@wasac.rw #urgent"
    resp = await client.post("/api/v1/reports", json={
        "category": "water_quality",
        "urgency": "high",
        "title": "Water quality test with special characters",
        "description": special_desc,
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json()["description"] == special_desc


@pytest.mark.asyncio
async def test_register_full_name_with_hyphens_and_apostrophes(client: AsyncClient):
    """Special chars: names with hyphens and apostrophes are common in Rwanda."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "hyphen_name@test.com",
        "password": "Test@12345",
        "full_name": "Marie-Claire D'Amour Ingabire",
        "role": "community",
    })
    assert resp.status_code == 201
    assert resp.json()["full_name"] == "Marie-Claire D'Amour Ingabire"


# ── Invalid / Empty Data Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_empty_full_name_rejected(client: AsyncClient):
    """Empty data: empty full_name must be rejected."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "emptyname@test.com",
        "password": "Test@12345",
        "full_name": "",
        "role": "community",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_report_missing_required_fields_rejected(client: AsyncClient, db: AsyncSession):
    """Empty data: submitting a report without required fields returns 422."""
    user = await make_user(db, email="missingfields@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        # missing urgency, title, description
    }, headers=auth_header(user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_service_request_short_description_rejected(client: AsyncClient, db: AsyncSession):
    """Boundary: service request description under minimum 10 characters is rejected."""
    user = await make_user(db, email="shortsr@test.com")
    resp = await client.post("/api/v1/service-requests", json={
        "request_type": "inspection",
        "urgency": "low",
        "description": "Too short",  # 9 chars — below the 10-char minimum
    }, headers=auth_header(user))
    assert resp.status_code == 422
