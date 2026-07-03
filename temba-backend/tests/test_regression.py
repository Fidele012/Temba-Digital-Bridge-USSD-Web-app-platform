"""
Regression tests — verifying that new features and updates have not broken
existing functionality.

Strategy: regression testing re-runs a canonical set of critical paths after
each development iteration to catch unintended side-effects. These tests cover
the features that were present in earlier versions of the platform and must
continue to work correctly after every new addition (priority classification,
anonymous rating, USSD expansion, dashboard updates, etc.).
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole

USSD = "/api/v1/ussd/callback"


# ── After adding priority classification (FR6) ───────────────────────────────

@pytest.mark.asyncio
async def test_regression_report_creation_still_works(client: AsyncClient, db: AsyncSession):
    """
    Regression: adding P1/P2/P3 classification must not break basic report
    creation. Report is created, status is 'open', reference number present.
    """
    user = await make_user(db, email="reg_report@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "medium",
        "title": "Regression test pipe burst report",
        "description": "This is a regression test to ensure report creation is unbroken",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "open"
    assert data["reference_number"] is not None


# ── After adding anonymous ratings ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_auth_endpoints_still_work(client: AsyncClient, db: AsyncSession):
    """
    Regression: after adding rating model and schema, authentication endpoints
    must still return the correct fields and status codes.
    """
    resp = await client.post("/api/v1/auth/register", json={
        "email": "reg_auth@test.com",
        "password": "Regression@123",
        "full_name": "Regression User",
        "role": "community",
    })
    assert resp.status_code == 201
    assert "hashed_password" not in resp.json()

    login = await client.post("/api/v1/auth/login", json={
        "email": "reg_auth@test.com",
        "password": "Regression@123",
    })
    assert login.status_code == 200
    assert "access_token" in login.json()
    assert "refresh_token" in login.json()


# ── After USSD expansion ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_ussd_welcome_still_works(client: AsyncClient):
    """
    Regression: after expanding USSD menus for sector/cell/village, the
    welcome screen must still respond with Temba branding and CON prompt.
    """
    resp = await client.post(USSD, data={
        "sessionId": "reg-ussd-001",
        "serviceCode": "*384*36640#",
        "phoneNumber": "+250780099001",
        "text": "",
    })
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "Temba" in resp.text


# ── After dashboard updates ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_service_request_creation_still_works(client: AsyncClient, db: AsyncSession):
    """
    Regression: after adding resolution_submitted status and notification
    features, basic service request creation must remain unchanged.
    """
    user = await make_user(db, email="reg_sr@test.com")
    resp = await client.post("/api/v1/service-requests", json={
        "request_type": "meter_support",
        "urgency": "medium",
        "description": "Regression test for meter support request creation",
        "province": "Kigali City",
        "district": "Gasabo",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json()["status"] == "submitted"
    assert resp.json()["request_type"] == "meter_support"


# ── After meeting_type fix ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_appointment_meeting_types_all_work(client: AsyncClient, db: AsyncSession):
    """
    Regression: after fixing meeting_type to correctly record phone_call and
    site_visit, all three meeting types must still be accepted by the API.
    """
    community = await make_user(db, email="reg_appt@test.com")
    prov_user = await make_user(db, email="reg_appt_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    for meeting_type in ("in_person", "phone_call", "site_visit"):
        resp = await client.post("/api/v1/appointments", json={
            "provider_id": str(provider.id),
            "reason": "consultation",
            "meeting_type": meeting_type,
            "appointment_date": "2026-09-20",
            "appointment_time": "10:00",
        }, headers=auth_header(community))
        assert resp.status_code == 201, f"meeting_type '{meeting_type}' rejected: {resp.status_code}"
        assert resp.json()["meeting_type"] == meeting_type


# ── After provider staff feature ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_provider_can_view_reports(client: AsyncClient, db: AsyncSession):
    """
    Regression: after adding ProviderStaff hierarchy and SLA escalation,
    providers must still be able to list reports assigned to them.
    """
    community = await make_user(db, email="reg_prov_view_comm@test.com")
    prov_user = await make_user(db, email="reg_prov_view_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    # Create a report assigned to this provider
    await client.post("/api/v1/reports", json={
        "category": "no_supply",
        "urgency": "medium",
        "title": "Regression test — no water supply report",
        "description": "Regression check that providers still see assigned reports correctly",
        "provider_id": str(provider.id),
    }, headers=auth_header(community))

    prov_reports = await client.get("/api/v1/reports", headers=auth_header(prov_user))
    assert prov_reports.status_code == 200
    assert len(prov_reports.json()["items"]) >= 1


# ── Health check always passes ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regression_health_check(client: AsyncClient):
    """
    Regression: the /health endpoint must always respond 200 after any update.
    This is the first check run in CI after every deployment.
    """
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
