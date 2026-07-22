"""
Functional tests — verifying that each required feature (FR1–FR17) of the
Temba Digital Bridge platform works correctly.

Strategy: functional testing checks that the software satisfies its specified
requirements, treating the system as a black box and validating outputs against
expected behaviour for each defined feature.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole


# ── FR1: Community member registration (web) ─────────────────────────────────

@pytest.mark.asyncio
async def test_fr1_community_registration_with_location(client: AsyncClient):
    """FR1: Community member can register with email, password, and Rwanda location."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "fr1_comm@test.com",
        "phone": "+250780000105",
        "password": "Functional@123",
        "full_name": "Marie Uwimana",
        "role": "community",
        "province": "Eastern Province",
        "district": "Nyagatare",
        "sector": "Karangazi",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "fr1_comm@test.com"
    assert data["province"] == "Eastern Province"
    assert data["district"] == "Nyagatare"


@pytest.mark.asyncio
async def test_fr1_provider_registration(client: AsyncClient):
    """FR1 + FR2: Water service provider can register with organisation details."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "fr1_prov@test.com",
        "phone": "+250780000106",
        "password": "Provider@123",
        "full_name": "WASAC Admin",
        "role": "provider",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "provider"


# ── FR5: Report category and urgency selection ────────────────────────────────

@pytest.mark.asyncio
async def test_fr5_report_with_category_and_urgency(client: AsyncClient, db: AsyncSession):
    """FR5: Community member can select category, urgency, and submit a report."""
    user = await make_user(db, email="fr5@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "high",
        "title": "Burst pipe flooding community road",
        "description": "A major pipe burst is flooding the main road near the community centre",
        "province": "Kigali City",
        "district": "Kicukiro",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "pipe_burst"
    assert data["urgency"] == "high"


# ── FR6: Auto priority classification ────────────────────────────────────────

@pytest.mark.asyncio
async def test_fr6_p1_auto_assigned_for_contamination(client: AsyncClient, db: AsyncSession):
    """FR6: Contamination reports are automatically classified P1 (4-hour SLA)."""
    user = await make_user(db, email="fr6_p1@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "contamination",
        "urgency": "medium",
        "title": "Water contamination detected in borehole",
        "description": "Residents in the area have reported unusual taste and smell in drinking water",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data.get("priority_class") == "P1"
    assert data.get("sla_deadline") is not None


@pytest.mark.asyncio
async def test_fr6_p3_auto_assigned_for_billing(client: AsyncClient, db: AsyncSession):
    """FR6: Billing complaints are classified P3 (72-hour SLA)."""
    user = await make_user(db, email="fr6_p3@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "billing",
        "urgency": "low",
        "title": "Incorrect billing amount on my statement",
        "description": "My water bill this month shows double the normal amount without explanation",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json().get("priority_class") == "P3"


# ── FR7: Reference number generation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_fr7_reference_number_generated_on_create(client: AsyncClient, db: AsyncSession):
    """FR7: Every report receives a unique reference number in format RPT-YYYYMMDD-XXXX."""
    user = await make_user(db, email="fr7@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "no_supply",
        "urgency": "high",
        "title": "No water supply for three consecutive days",
        "description": "Our entire neighbourhood has had no water supply for three consecutive days",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    ref = resp.json().get("reference_number")
    assert ref is not None
    assert ref.startswith("RPT-")
    parts = ref.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 4  # unique suffix


# ── FR8: Public tracking without login ───────────────────────────────────────

@pytest.mark.asyncio
async def test_fr8_public_tracking_requires_no_login(client: AsyncClient, db: AsyncSession):
    """FR8: Any person can track a report by reference code without authenticating."""
    user = await make_user(db, email="fr8@test.com")
    create = await client.post("/api/v1/reports", json={
        "category": "low_pressure",
        "urgency": "medium",
        "title": "Very low water pressure all day",
        "description": "Water pressure has been very low throughout the day making it hard to use",
    }, headers=auth_header(user))
    ref = create.json()["reference_number"]

    # No auth header — completely public
    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    assert track.json()["reference_number"] == ref


# ── FR11: Provider status update workflow ────────────────────────────────────

@pytest.mark.asyncio
async def test_fr11_provider_updates_report_status(client: AsyncClient, db: AsyncSession):
    """FR11: Provider can update report through Open → Acknowledged → In Progress."""
    community = await make_user(db, email="fr11_comm@test.com")
    prov_user = await make_user(db, email="fr11_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    create = await client.post("/api/v1/reports", json={
        "category": "meter",
        "urgency": "low",
        "title": "Faulty meter reading causing high bills",
        "description": "Meter is showing incorrect readings resulting in inflated water bills",
        "provider_id": str(provider.id),
    }, headers=auth_header(community))
    report_id = create.json()["id"]

    ack = await client.put(f"/api/v1/reports/{report_id}", json={
        "status": "acknowledged",
    }, headers=auth_header(prov_user))
    assert ack.json()["status"] == "acknowledged"


# ── FR15: Appointment booking ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fr15_appointment_booking(client: AsyncClient, db: AsyncSession):
    """FR15: Community member can book an appointment with date, time, and provider."""
    community = await make_user(db, email="fr15_appt@test.com")
    prov_user = await make_user(db, email="fr15_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    resp = await client.post("/api/v1/appointments", json={
        "provider_id": str(provider.id),
        "reason": "inspection",
        "meeting_type": "phone_call",
        "appointment_date": "2026-09-10",
        "appointment_time": "14:00",
    }, headers=auth_header(community))
    assert resp.status_code == 201
    data = resp.json()
    assert data["reason"] == "inspection"
    assert data["meeting_type"] == "phone_call"
    assert data["status"] == "pending"


# ── FR15: Service request submission ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_fr15_service_request_submission(client: AsyncClient, db: AsyncSession):
    """FR15: Community member can submit a service request with type and urgency."""
    user = await make_user(db, email="fr15_sr@test.com")
    resp = await client.post("/api/v1/service-requests", json={
        "request_type": "tank_delivery",
        "urgency": "high",
        "description": "Need emergency water tank delivery for the health centre",
        "province": "Southern Province",
        "district": "Huye",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json()["request_type"] == "tank_delivery"
    assert resp.json()["status"] == "submitted"


# ── FR16: Password change ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fr16_password_change(client: AsyncClient, db: AsyncSession):
    """FR16: Authenticated user can change their password."""
    user = await make_user(db, email="fr16@test.com", password="OldPass@123")
    resp = await client.post("/api/v1/auth/change-password", json={
        "current_password": "OldPass@123",
        "new_password": "NewPass@456",
    }, headers=auth_header(user))
    assert resp.status_code == 200

    # New password works for login
    login = await client.post("/api/v1/auth/login", json={
        "email": "fr16@test.com",
        "password": "NewPass@456",
    })
    assert login.status_code == 200
