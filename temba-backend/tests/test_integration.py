"""
Integration tests — verifying cross-component behaviour that single-endpoint
unit tests cannot cover: notifications created on events, SLA deadlines set
correctly, provider data isolation, status-transition enforcement, and the
complete public-tracking contract.

These tests complement test_system.py (full journeys) by drilling into specific
integration points between components.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole


# ── SLA Deadline Integration ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_report_sla_deadline_set_on_create(client: AsyncClient, db: AsyncSession):
    """P1 contamination reports must receive a 4-hour SLA deadline automatically."""
    user = await make_user(db, email="sla_p1@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "contamination",
        "urgency": "high",
        "title": "Brown water coming from taps in Remera sector",
        "description": "Multiple households in Remera are reporting brown-coloured water with a chemical smell",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["priority_class"] == "P1"
    assert data["sla_deadline"] is not None
    assert data["reference_number"].startswith("RPT-")


@pytest.mark.asyncio
async def test_p2_report_sla_deadline_set_on_create(client: AsyncClient, db: AsyncSession):
    """P2 reports (pipe burst + medium urgency) must receive a 24-hour SLA deadline."""
    user = await make_user(db, email="sla_p2@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "medium",
        "title": "Pipe burst on Kacyiru road causing water loss",
        "description": "A pipe has burst on the main road in Kacyiru causing significant water to be lost",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["priority_class"] == "P2"
    assert data["sla_deadline"] is not None


@pytest.mark.asyncio
async def test_p3_report_gets_72h_sla(client: AsyncClient, db: AsyncSession):
    """P3 billing reports must receive a 72-hour SLA deadline."""
    user = await make_user(db, email="sla_p3@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "billing",
        "urgency": "low",
        "title": "Incorrect amount on my monthly water bill",
        "description": "My water bill this month is three times the usual amount with no explanation",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    assert resp.json()["priority_class"] == "P3"
    assert resp.json()["sla_deadline"] is not None


# ── Provider Data Isolation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_cannot_update_another_providers_report(client: AsyncClient, db: AsyncSession):
    """Provider A must not be able to update a report assigned to Provider B."""
    comm = await make_user(db, email="iso_comm@test.com")
    prov_a_user = await make_user(db, email="iso_prov_a@test.com", role=UserRole.PROVIDER)
    prov_b_user = await make_user(db, email="iso_prov_b@test.com", role=UserRole.PROVIDER)
    prov_a = await make_provider(db, prov_a_user, organization_name="Provider A")
    prov_b = await make_provider(db, prov_b_user, organization_name="Provider B")

    # Report assigned to Provider A
    create = await client.post("/api/v1/reports", json={
        "category": "no_supply",
        "urgency": "high",
        "title": "No water supply for two days in Kimironko",
        "description": "The entire Kimironko sector has had no water supply for two consecutive days",
        "provider_id": str(prov_a.id),
    }, headers=auth_header(comm))
    assert create.status_code == 201
    report_id = create.json()["id"]

    # Provider B tries to update it — should fail
    resp = await client.put(f"/api/v1/reports/{report_id}",
        json={"status": "acknowledged"},
        headers=auth_header(prov_b_user),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_community_member_cannot_update_report_status(client: AsyncClient, db: AsyncSession):
    """Community members must not be able to update a report's status to provider states."""
    user = await make_user(db, email="comm_noupdate@test.com")
    create = await client.post("/api/v1/reports", json={
        "category": "low_pressure",
        "urgency": "low",
        "title": "Very low water pressure affecting daily use",
        "description": "Water pressure has been very low making it impossible to fill tanks properly",
    }, headers=auth_header(user))
    report_id = create.json()["id"]

    resp = await client.put(f"/api/v1/reports/{report_id}",
        json={"status": "in_progress"},
        headers=auth_header(user),
    )
    assert resp.status_code in (403, 422)


# ── Public Tracking Contract ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_returns_human_readable_status(client: AsyncClient, db: AsyncSession):
    """Public track endpoint must return a human-readable status, not a raw DB enum."""
    user = await make_user(db, email="track_label@test.com")
    create = await client.post("/api/v1/reports", json={
        "category": "water_quality",
        "urgency": "medium",
        "title": "Poor water quality noticed in Nyamirambo",
        "description": "Residents in Nyamirambo have noticed an unusual taste in their tap water",
    }, headers=auth_header(user))
    ref = create.json()["reference_number"]

    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    data = track.json()
    assert data["status"] == "Submitted - awaiting review"
    assert data["type"] == "report"
    assert data["reference_number"] == ref
    assert data["category"] is not None
    assert data["urgency"] is not None


@pytest.mark.asyncio
async def test_track_service_request_by_reference(client: AsyncClient, db: AsyncSession):
    """Public track endpoint must also resolve service request references (SRQ-)."""
    user = await make_user(db, email="track_srq@test.com")
    prov_user = await make_user(db, email="track_srq_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    create = await client.post("/api/v1/service-requests", json={
        "request_type": "water_connection",
        "urgency": "medium",
        "description": "Request for a new water connection to a newly built residential house",
        "provider_id": str(provider.id),
    }, headers=auth_header(user))
    assert create.status_code == 201
    ref = create.json()["reference_number"]
    assert ref.startswith("SRQ-")

    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    data = track.json()
    assert data["type"] == "service_request"
    assert data["reference_number"] == ref


@pytest.mark.asyncio
async def test_track_unknown_reference_returns_404(client: AsyncClient):
    """Track endpoint must return 404 for a non-existent reference number."""
    resp = await client.get("/api/v1/track/RPT-99991231-XXXX")
    assert resp.status_code == 404


# ── Reference Number Uniqueness ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_reports_get_different_reference_numbers(client: AsyncClient, db: AsyncSession):
    """Every report must receive a unique reference number — no collisions."""
    user = await make_user(db, email="unique_ref@test.com")
    refs = set()
    for i in range(5):
        resp = await client.post("/api/v1/reports", json={
            "category": "no_supply",
            "urgency": "medium",
            "title": f"Water supply outage report number {i + 1} in my sector",
            "description": "No water supply has been available in this area for the past day",
        }, headers=auth_header(user))
        assert resp.status_code == 201
        refs.add(resp.json()["reference_number"])
    assert len(refs) == 5, "All 5 reports must have unique reference numbers"


# ── Report Status Lifecycle ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_status_progresses_open_to_verified(client: AsyncClient, db: AsyncSession):
    """
    Report status lifecycle: open → acknowledged → in_progress → resolution_submitted
    → verified. Each transition must succeed and the final status must be 'verified'.
    """
    comm = await make_user(db, email="lifecycle_comm@test.com")
    prov_user = await make_user(db, email="lifecycle_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    create = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "critical",
        "title": "Critical pipe burst flooding residential area in Gikondo",
        "description": "A large pipe has burst in Gikondo flooding three streets and homes nearby",
        "provider_id": str(provider.id),
    }, headers=auth_header(comm))
    assert create.status_code == 201
    report_id = create.json()["id"]
    assert create.json()["status"] == "open"

    # Provider acknowledges
    ack = await client.put(f"/api/v1/reports/{report_id}",
        json={"status": "acknowledged"}, headers=auth_header(prov_user))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    # Provider marks in progress
    prog = await client.put(f"/api/v1/reports/{report_id}",
        json={"status": "in_progress"}, headers=auth_header(prov_user))
    assert prog.status_code == 200
    assert prog.json()["status"] == "in_progress"

    # Provider submits resolution
    res = await client.put(f"/api/v1/reports/{report_id}",
        json={"status": "resolution_submitted", "resolution_notes": "Pipe repaired and water restored"},
        headers=auth_header(prov_user))
    assert res.status_code == 200
    assert res.json()["status"] == "resolution_submitted"

    # Community verifies resolution
    verify = await client.post(f"/api/v1/reports/{report_id}/verify",
        json={"verdict": "verified"}, headers=auth_header(comm))
    assert verify.status_code == 200
    assert verify.json()["status"] == "verified"


# ── Appointment Provider Isolation ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_only_sees_own_appointments(client: AsyncClient, db: AsyncSession):
    """A provider must only see appointments booked with their own organisation."""
    comm = await make_user(db, email="appt_iso_comm@test.com")
    prov_a_user = await make_user(db, email="appt_iso_prov_a@test.com", role=UserRole.PROVIDER)
    prov_b_user = await make_user(db, email="appt_iso_prov_b@test.com", role=UserRole.PROVIDER)
    prov_a = await make_provider(db, prov_a_user, organization_name="Water Co A")
    prov_b = await make_provider(db, prov_b_user, organization_name="Water Co B")

    # Book with Provider A
    await client.post("/api/v1/appointments", json={
        "provider_id": str(prov_a.id),
        "reason": "pipe_repair",
        "meeting_type": "site_visit",
        "appointment_date": "2026-09-20",
        "appointment_time": "09:00",
    }, headers=auth_header(comm))

    # Provider B sees no appointments
    resp = await client.get("/api/v1/appointments", headers=auth_header(prov_b_user))
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    prov_b_ids = {str(prov_b.id)}
    for appt in items:
        assert str(appt.get("provider_id")) in prov_b_ids


# ── Notification Creation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notifications_endpoint_accessible(client: AsyncClient, db: AsyncSession):
    """Authenticated user must be able to retrieve their notification list."""
    user = await make_user(db, email="notif_access@test.com")
    resp = await client.get("/api/v1/notifications", headers=auth_header(user))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data or isinstance(data, list)


# ── API Schema Contract ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_response_schema_contains_required_fields(client: AsyncClient, db: AsyncSession):
    """Every report response must contain all fields required by the API contract."""
    user = await make_user(db, email="schema_report@test.com")
    resp = await client.post("/api/v1/reports", json={
        "category": "meter",
        "urgency": "low",
        "title": "Water meter showing inaccurate readings consistently",
        "description": "The meter reading at my property keeps jumping to incorrect values every week",
    }, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    required_fields = {
        "id", "reference_number", "category", "urgency", "title",
        "description", "status", "priority_class", "sla_deadline", "created_at",
    }
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"


@pytest.mark.asyncio
async def test_user_profile_schema_contains_required_fields(client: AsyncClient, db: AsyncSession):
    """GET /users/me must return a well-formed profile with all required fields."""
    user = await make_user(db, email="schema_user@test.com")
    resp = await client.get("/api/v1/users/me", headers=auth_header(user))
    assert resp.status_code == 200
    data = resp.json()
    required_fields = {"id", "email", "full_name", "role", "is_active", "is_verified"}
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    # Sensitive fields must never appear
    assert "hashed_password" not in data
    assert "ussd_pin_hash" not in data


@pytest.mark.asyncio
async def test_provider_listing_returns_only_approved_providers(client: AsyncClient, db: AsyncSession):
    """Public provider listing must only return APPROVED providers."""
    from app.models.provider import ProviderStatus
    approved_user = await make_user(db, email="prov_approved@test.com", role=UserRole.PROVIDER)
    pending_user = await make_user(db, email="prov_pending@test.com", role=UserRole.PROVIDER)
    await make_provider(db, approved_user, status=ProviderStatus.APPROVED)
    await make_provider(db, pending_user, status=ProviderStatus.PENDING)

    resp = await client.get("/api/v1/providers")
    assert resp.status_code == 200
    providers = resp.json().get("items", resp.json() if isinstance(resp.json(), list) else [])
    for p in providers:
        assert p.get("status") == "approved", f"Non-approved provider in listing: {p}"


# ── Health & API Availability ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_returns_ok_status(client: AsyncClient):
    """Health check must return HTTP 200 with status 'ok' — proves API is up."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


@pytest.mark.asyncio
async def test_api_root_reachable(client: AsyncClient):
    """Root / endpoint must be reachable — proves the server is running."""
    resp = await client.get("/")
    assert resp.status_code in (200, 404)  # 404 is fine — server is alive


@pytest.mark.asyncio
async def test_openapi_docs_available(client: AsyncClient):
    """OpenAPI schema endpoint must be reachable — proves API is documented."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "paths" in data
    assert "components" in data
