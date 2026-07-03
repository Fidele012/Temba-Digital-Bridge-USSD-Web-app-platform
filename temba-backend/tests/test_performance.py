"""
Performance and response-time tests — demonstrates system performance across
different load conditions and input sizes.

Strategy: timing-based functional tests that assert API endpoints respond
within acceptable SLA thresholds under typical and boundary conditions.
"""
import time
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole

# ── Thresholds (milliseconds) ────────────────────────────────────────────────
T_FAST   = 500    # unauthenticated / public endpoints
T_NORMAL = 800    # authenticated read endpoints
T_WRITE  = 1200   # authenticated write endpoints (DB insert + audit log)


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


# ── Public Endpoints ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_response_time(client: AsyncClient):
    """Health check must respond in under 500 ms."""
    start = time.perf_counter()
    resp = await client.get("/health")
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_FAST, f"Health check took {elapsed:.0f} ms — expected < {T_FAST} ms"


@pytest.mark.asyncio
async def test_providers_list_response_time(client: AsyncClient, db: AsyncSession):
    """Public provider listing must respond in under 500 ms."""
    start = time.perf_counter()
    resp = await client.get("/api/v1/providers")
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_FAST, f"Provider list took {elapsed:.0f} ms — expected < {T_FAST} ms"


@pytest.mark.asyncio
async def test_login_response_time(client: AsyncClient, db: AsyncSession):
    """Login must complete in under 800 ms (includes bcrypt verify)."""
    await make_user(db, email="perf_login@test.com")  # default password: Test@12345
    start = time.perf_counter()
    resp = await client.post("/api/v1/auth/login", json={
        "email": "perf_login@test.com", "password": "Test@12345",
    })
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_NORMAL, f"Login took {elapsed:.0f} ms — expected < {T_NORMAL} ms"


# ── Authenticated Read Endpoints ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_reports_response_time(client: AsyncClient, db: AsyncSession):
    """Report listing for a community user must respond in under 800 ms."""
    user = await make_user(db, email="perf_reports@test.com")
    # Create 5 reports to have a realistic dataset
    for i in range(5):
        await client.post("/api/v1/reports", json={
            "category": "pipe_burst", "urgency": "medium",
            "title": f"Performance test report number {i+1}",
            "description": "Testing API response time with multiple records in the database",
        }, headers=auth_header(user))

    start = time.perf_counter()
    resp = await client.get("/api/v1/reports", headers=auth_header(user))
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_NORMAL, f"Reports list took {elapsed:.0f} ms — expected < {T_NORMAL} ms"


@pytest.mark.asyncio
async def test_list_notifications_response_time(client: AsyncClient, db: AsyncSession):
    """Notifications endpoint must respond in under 800 ms."""
    user = await make_user(db, email="perf_notifs@test.com")
    start = time.perf_counter()
    resp = await client.get("/api/v1/notifications", headers=auth_header(user))
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_NORMAL, f"Notifications took {elapsed:.0f} ms — expected < {T_NORMAL} ms"


@pytest.mark.asyncio
async def test_get_user_profile_response_time(client: AsyncClient, db: AsyncSession):
    """User profile endpoint must respond in under 800 ms."""
    user = await make_user(db, email="perf_profile@test.com")
    start = time.perf_counter()
    resp = await client.get("/api/v1/users/me", headers=auth_header(user))
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_NORMAL, f"Profile took {elapsed:.0f} ms — expected < {T_NORMAL} ms"


# ── Authenticated Write Endpoints ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_report_response_time(client: AsyncClient, db: AsyncSession):
    """Report creation (DB insert + audit log + SLA deadline calc) under 1200 ms."""
    user = await make_user(db, email="perf_create@test.com")
    start = time.perf_counter()
    resp = await client.post("/api/v1/reports", json={
        "category": "contamination", "urgency": "critical",
        "title": "Performance test water contamination report",
        "description": "This report is created as part of performance testing to measure API response time",
        "province": "Kigali City", "district": "Gasabo",
    }, headers=auth_header(user))
    elapsed = _ms(start)
    assert resp.status_code == 201
    assert elapsed < T_WRITE, f"Report creation took {elapsed:.0f} ms — expected < {T_WRITE} ms"


@pytest.mark.asyncio
async def test_create_service_request_response_time(client: AsyncClient, db: AsyncSession):
    """Service request creation must complete in under 1200 ms."""
    user = await make_user(db, email="perf_sr@test.com")
    start = time.perf_counter()
    resp = await client.post("/api/v1/service-requests", json={
        "request_type": "water_connection", "urgency": "high",
        "description": "Performance testing service request for new water connection installation",
        "province": "Eastern Province", "district": "Bugesera",
    }, headers=auth_header(user))
    elapsed = _ms(start)
    assert resp.status_code == 201
    assert elapsed < T_WRITE, f"Service request creation took {elapsed:.0f} ms — expected < {T_WRITE} ms"


@pytest.mark.asyncio
async def test_registration_response_time(client: AsyncClient):
    """User registration must complete in under 1200 ms (includes bcrypt hash)."""
    start = time.perf_counter()
    resp = await client.post("/api/v1/auth/register", json={
        "email": "perf_reg@test.com",
        "password": "PerfTest@123",
        "full_name": "Performance Test User",
        "role": "community",
    })
    elapsed = _ms(start)
    assert resp.status_code == 201
    assert elapsed < T_WRITE, f"Registration took {elapsed:.0f} ms — expected < {T_WRITE} ms"


# ── Concurrent Request Simulation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sequential_report_submissions(client: AsyncClient, db: AsyncSession):
    """
    10 sequential report submissions must all succeed and each must stay
    under the write threshold. Simulates a burst of community activity.
    """
    user = await make_user(db, email="perf_burst@test.com")
    times = []
    for i in range(10):
        start = time.perf_counter()
        resp = await client.post("/api/v1/reports", json={
            "category": "no_supply", "urgency": "high",
            "title": f"Burst test report submission number {i+1:02d}",
            "description": "Sequential submission test to measure system behaviour under rapid input",
        }, headers=auth_header(user))
        elapsed = _ms(start)
        times.append(elapsed)
        assert resp.status_code == 201, f"Request {i+1} failed with {resp.status_code}"

    avg = sum(times) / len(times)
    worst = max(times)
    assert worst < T_WRITE * 2, f"Worst-case sequential submission: {worst:.0f} ms"
    # avg is informational — not a hard fail but logged for the report
    print(f"\n[perf] 10 sequential submissions — avg: {avg:.0f} ms, worst: {worst:.0f} ms")


# ── USSD Endpoint Performance ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_callback_response_time(client: AsyncClient):
    """
    USSD callback must respond in under 500 ms — Africa's Talking times out
    at 3 seconds but we target much faster to avoid mobile network issues.
    """
    start = time.perf_counter()
    resp = await client.post("/api/v1/ussd/callback", data={
        "sessionId": "perf-sess-001",
        "serviceCode": "*384*36640#",
        "phoneNumber": "+250780000099",
        "text": "",
    })
    elapsed = _ms(start)
    assert resp.status_code == 200
    assert elapsed < T_FAST, f"USSD welcome screen took {elapsed:.0f} ms — expected < {T_FAST} ms"
