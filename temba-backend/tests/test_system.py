"""
System tests — testing the complete application end-to-end.

Strategy: each test simulates a full user journey through the entire stack
(HTTP → FastAPI → SQLAlchemy → SQLite → response), verifying that all
components work together correctly as a single system.

Journeys tested:
  1. Community member: register → login → submit report → get reference code → track publicly
  2. Community member: register → book appointment → provider approves
  3. Community member: register → submit service request → provider acknowledges
  4. Provider: receives report assigned to their organisation
  5. Public tracker: find report by reference without logging in
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole


# ── Journey 1: Full Report Submission and Public Tracking ────────────────────

@pytest.mark.asyncio
async def test_full_community_report_journey(client: AsyncClient, db: AsyncSession):
    """
    System test: register → login → submit report → receive reference code
    → track the report publicly without logging in.
    Covers FR1, FR5, FR7, FR8.
    """
    # Step 1: Register
    reg = await client.post("/api/v1/auth/register", json={
        "email": "system_journey@test.com",
        "password": "Journey@123",
        "full_name": "Jean Mutabazi",
        "role": "community",
        "province": "Eastern Province",
        "district": "Nyagatare",
    })
    assert reg.status_code == 201

    # Step 2: Login
    login = await client.post("/api/v1/auth/login", json={
        "email": "system_journey@test.com",
        "password": "Journey@123",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 3: Submit report
    report = await client.post("/api/v1/reports", json={
        "category": "contamination",
        "urgency": "critical",
        "title": "Water has unusual smell and colour",
        "description": "The tap water in Karangazi Sector has an unusual brown colour and smell since yesterday morning",
        "province": "Eastern Province",
        "district": "Nyagatare",
    }, headers=headers)
    assert report.status_code == 201
    data = report.json()

    # Step 4: Reference code is present and correctly formatted
    ref = data.get("reference_number")
    assert ref is not None
    assert ref.startswith("RPT-")

    # Step 5: Priority was auto-classified (contamination → P1)
    assert data.get("priority_class") == "P1"

    # Step 6: Track publicly without any token (FR8)
    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    tracked = track.json()
    assert tracked["reference_number"] == ref
    assert tracked["status"] == "open"


# ── Journey 2: Appointment Booking and Provider Approval ─────────────────────

@pytest.mark.asyncio
async def test_full_appointment_journey(client: AsyncClient, db: AsyncSession):
    """
    System test: community member books appointment → provider approves →
    community sees approved status.
    Covers FR15.
    """
    community = await make_user(db, email="sys_appt_comm@test.com")
    prov_user = await make_user(db, email="sys_appt_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    # Book appointment
    resp = await client.post("/api/v1/appointments", json={
        "provider_id": str(provider.id),
        "reason": "pipe_repair",
        "meeting_type": "site_visit",
        "appointment_date": "2026-08-15",
        "appointment_time": "09:00",
        "notes": "Please come in the morning",
    }, headers=auth_header(community))
    assert resp.status_code == 201
    appt_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"
    assert resp.json()["meeting_type"] == "site_visit"

    # Provider approves
    approve = await client.put(
        f"/api/v1/appointments/{appt_id}/status",
        json={"status": "approved"},
        headers=auth_header(prov_user),
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Community member sees it as approved
    my_appts = await client.get("/api/v1/appointments", headers=auth_header(community))
    assert my_appts.status_code == 200
    statuses = [a["status"] for a in my_appts.json()["items"]]
    assert "approved" in statuses


# ── Journey 3: Service Request End-to-End ────────────────────────────────────

@pytest.mark.asyncio
async def test_full_service_request_journey(client: AsyncClient, db: AsyncSession):
    """
    System test: community member submits service request → provider
    acknowledges → community sees updated status.
    Covers FR15.
    """
    community = await make_user(db, email="sys_sr_comm@test.com")
    prov_user = await make_user(db, email="sys_sr_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    # Submit
    resp = await client.post("/api/v1/service-requests", json={
        "request_type": "water_connection",
        "urgency": "high",
        "description": "Need a new water connection for our household in Nyagatare",
        "provider_id": str(provider.id),
        "province": "Eastern Province",
        "district": "Nyagatare",
    }, headers=auth_header(community))
    assert resp.status_code == 201
    sr_id = resp.json()["id"]
    assert resp.json()["status"] == "submitted"

    # Provider acknowledges
    ack = await client.put(f"/api/v1/service-requests/{sr_id}", json={
        "status": "acknowledged",
    }, headers=auth_header(prov_user))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    # Community sees acknowledged
    my_srs = await client.get("/api/v1/service-requests", headers=auth_header(community))
    assert my_srs.status_code == 200
    found = next((s for s in my_srs.json()["items"] if s["id"] == sr_id), None)
    assert found is not None
    assert found["status"] == "acknowledged"


# ── Journey 4: Provider Views Assigned Reports ───────────────────────────────

@pytest.mark.asyncio
async def test_provider_sees_assigned_reports(client: AsyncClient, db: AsyncSession):
    """
    System test: community member submits report assigned to provider →
    provider's report list includes it.
    Covers FR9, FR10.
    """
    community = await make_user(db, email="sys_prov_comm@test.com")
    prov_user = await make_user(db, email="sys_prov_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    # Submit report assigned to provider
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "high",
        "title": "Burst water pipe on main road",
        "description": "Water is flooding the road outside the community hall in the sector",
        "provider_id": str(provider.id),
    }, headers=auth_header(community))
    assert resp.status_code == 201
    report_id = resp.json()["id"]

    # Provider lists reports
    prov_reports = await client.get("/api/v1/reports", headers=auth_header(prov_user))
    assert prov_reports.status_code == 200
    ids = [r["id"] for r in prov_reports.json()["items"]]
    assert report_id in ids


# ── Journey 5: Report Status Lifecycle ───────────────────────────────────────

@pytest.mark.asyncio
async def test_report_status_update_lifecycle(client: AsyncClient, db: AsyncSession):
    """
    System test: provider updates report through the full status lifecycle.
    Covers FR11.
    """
    community = await make_user(db, email="sys_lifecycle_comm@test.com")
    prov_user = await make_user(db, email="sys_lifecycle_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    # Submit
    resp = await client.post("/api/v1/reports", json={
        "category": "no_supply",
        "urgency": "high",
        "title": "No water supply in the whole village",
        "description": "Water supply has been cut off since two days ago with no explanation from provider",
        "provider_id": str(provider.id),
    }, headers=auth_header(community))
    report_id = resp.json()["id"]

    # Acknowledge
    ack = await client.put(f"/api/v1/reports/{report_id}", json={
        "status": "acknowledged",
    }, headers=auth_header(prov_user))
    assert ack.json()["status"] == "acknowledged"

    # Move to in_progress
    prog = await client.put(f"/api/v1/reports/{report_id}", json={
        "status": "in_progress",
    }, headers=auth_header(prov_user))
    assert prog.json()["status"] == "in_progress"

    # Submit resolution
    res = await client.put(f"/api/v1/reports/{report_id}", json={
        "status": "resolution_submitted",
        "resolution_notes": "Water supply restored. Root cause was a broken valve near the main junction.",
    }, headers=auth_header(prov_user))
    assert res.json()["status"] == "resolution_submitted"
    assert res.json()["resolution_notes"] is not None
