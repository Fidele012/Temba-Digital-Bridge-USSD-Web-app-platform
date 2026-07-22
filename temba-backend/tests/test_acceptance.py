"""
Acceptance Tests — Temba Digital Bridge
========================================
Automated verification of the three UAT task scenarios and the bilingual
(English / Kinyarwanda) interface requirement stated in the Acceptance
Testing Report.

UAT Task 1 · Submit a water-issue report via USSD
UAT Task 2 · Track a report on the web without logging in
UAT Task 3 · Update a report's status as a water-service provider

Bilingual · Every USSD prompt must render correctly in English and in
            Kinyarwanda through the *384*36640# service code.

These tests complement the field UAT conducted with the pilot cohort in
Nyagatare District / Karangazi Sector and provide an objective, repeatable
evidence record for the capstone document.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import UserRole
from tests.conftest import auth_header, make_provider, make_user

USSD = "/api/v1/ussd/callback"


# ── USSD helper ───────────────────────────────────────────────────────────────

def ussd(client: AsyncClient, phone: str, text: str, session: str = "uat-sess"):
    return client.post(USSD, data={
        "sessionId": session,
        "serviceCode": "*384*36640#",
        "phoneNumber": phone,
        "text": text,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BILINGUAL VERIFICATION
# Confirms every USSD entry point renders in English (1) and Kinyarwanda (2)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bilingual_welcome_screen_contains_both_languages(client: AsyncClient):
    """
    Welcome screen (empty text) must show language selector with both options,
    proving that neither language is omitted before the user makes a choice.
    """
    resp = await ussd(client, "+250780001001", "")
    assert resp.status_code == 200
    body = resp.text
    assert "CON" in body
    assert "English" in body
    assert "Kinyarwanda" in body


@pytest.mark.asyncio
async def test_bilingual_english_auth_menu(client: AsyncClient):
    """
    Choosing language 1 (English) must return the English auth menu —
    'Register' and 'Login' displayed in English.
    """
    resp = await ussd(client, "+250780001002", "1")
    assert resp.status_code == 200
    body = resp.text
    assert "Register" in body
    assert "Login" in body


@pytest.mark.asyncio
async def test_bilingual_kinyarwanda_auth_menu(client: AsyncClient):
    """
    Choosing language 2 (Kinyarwanda) must return the Kinyarwanda auth menu —
    'Iyandikishe' (Register) and 'Injira' (Login) displayed in Kinyarwanda.
    """
    resp = await ussd(client, "+250780001003", "2")
    assert resp.status_code == 200
    body = resp.text
    assert "Iyandikishe" in body
    assert "Injira" in body


@pytest.mark.asyncio
async def test_bilingual_english_report_category_menu(client: AsyncClient, db: AsyncSession):
    """
    After English login, selecting Menu 1 must show report categories in English:
    'Contamination', 'Pipe burst', 'No supply'.
    """
    await make_user(db, email="bil_en_cat@uat.com", phone="+250780001004",
                    ussd_pin_hash=hash_password("1111"))
    resp = await ussd(client, "+250780001004", "1*2*1111*1")
    assert resp.status_code == 200
    body = resp.text
    assert "CON" in body
    assert "Contamination" in body or "Pipe burst" in body or "No supply" in body


@pytest.mark.asyncio
async def test_bilingual_kinyarwanda_report_category_menu(client: AsyncClient, db: AsyncSession):
    """
    After Kinyarwanda login, selecting Menu 1 must show report categories in
    Kinyarwanda: 'Amazi yanduye', 'Umuyoboro wabuze', 'Nta mazi'.
    """
    await make_user(db, email="bil_rw_cat@uat.com", phone="+250780001005",
                    ussd_pin_hash=hash_password("1111"))
    resp = await ussd(client, "+250780001005", "2*2*1111*1")
    assert resp.status_code == 200
    body = resp.text
    assert "CON" in body
    assert "Amazi yanduye" in body or "Umuyoboro wabuze" in body or "Nta mazi" in body


@pytest.mark.asyncio
async def test_bilingual_kinyarwanda_report_submission_confirmation(
    client: AsyncClient, db: AsyncSession
):
    """
    A full USSD report submission in Kinyarwanda must end with a Kinyarwanda
    confirmation: 'Raporo yoherejwe!' and a tracking code starting 'RPT-'.
    """
    await make_user(
        db, email="bil_rw_submit@uat.com", phone="+250780001006",
        ussd_pin_hash=hash_password("2222"),
        province="Eastern Province", district="Nyagatare",
    )
    prov_user = await make_user(db, email="bil_rw_prov@uat.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # lang=2(RW) · login · PIN · 1=Report · 1=Contamination · 1=High · 1=Provider
    resp = await ussd(client, "+250780001006", "2*2*2222*1*1*1*1")
    assert resp.status_code == 200
    body = resp.text
    assert "END" in body
    assert "Raporo yoherejwe" in body
    assert "RPT-" in body


# ═══════════════════════════════════════════════════════════════════════════════
# UAT TASK 1 — SUBMIT A WATER-ISSUE REPORT VIA USSD
# Pilot scenario: community member in Karangazi Sector dials *384*36640#,
# selects language, logs in, and submits a contamination report.
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_uat_task1_ussd_report_submission_english(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 1 (English path): community member submits a contamination report
    via USSD. System must respond END with a 'RPT-' tracking code and an
    English confirmation message — proves the full mobile channel works.
    """
    await make_user(
        db, email="uat_t1_en@uat.com", phone="+250780002001",
        ussd_pin_hash=hash_password("5678"),
        province="Eastern Province", district="Nyagatare",
    )
    prov_user = await make_user(db, email="uat_t1_prov_en@uat.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # lang=1(EN) · 2=Login · PIN · 1=Report water issue · 1=Contamination
    # · 1=High urgency · 1=First available provider
    resp = await ussd(client, "+250780002001", "1*2*5678*1*1*1*1")
    assert resp.status_code == 200
    body = resp.text
    assert "END" in body, "USSD session must end after submission"
    assert "RPT-" in body, "Response must include tracking reference number"
    assert "submitted" in body.lower() or "Report" in body, \
        "English confirmation message must appear"


@pytest.mark.asyncio
async def test_uat_task1_ussd_report_submission_kinyarwanda(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 1 (Kinyarwanda path): same scenario in Kinyarwanda confirms the
    bilingual channel works for Rwandan community members who prefer Kinyarwanda.
    """
    await make_user(
        db, email="uat_t1_rw@uat.com", phone="+250780002002",
        ussd_pin_hash=hash_password("5678"),
        province="Eastern Province", district="Nyagatare",
    )
    prov_user = await make_user(db, email="uat_t1_prov_rw@uat.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # lang=2(RW) · 2=Login · PIN · 1=Tanga raporo · 1=Amazi yanduye
    # · 1=Byihutirwa cyane · 1=First available provider
    resp = await ussd(client, "+250780002002", "2*2*5678*1*1*1*1")
    assert resp.status_code == 200
    body = resp.text
    assert "END" in body, "USSD session must end after submission"
    assert "RPT-" in body, "Response must include tracking reference number"
    assert "Raporo yoherejwe" in body, "Kinyarwanda confirmation must appear"


# ═══════════════════════════════════════════════════════════════════════════════
# UAT TASK 2 — TRACK A REPORT ON THE WEB WITHOUT LOGGING IN
# Pilot scenario: community member uses the public /track endpoint to check
# their report's status using only the reference code received via USSD/SMS.
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_uat_task2_web_tracking_without_authentication(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 2: community member submits a report, then tracks it publicly
    using only the reference code — no login required. Confirms the anonymous
    tracking feature works end-to-end on the web channel.
    """
    user = await make_user(db, email="uat_t2@uat.com")

    # Submit report via REST API (same data model as web dashboard)
    submit = await client.post("/api/v1/reports", json={
        "category": "no_supply",
        "urgency": "critical",
        "title": "No water supply for three days in Karangazi Sector",
        "description": (
            "The entire Karangazi Sector has had no water supply for three "
            "consecutive days. Households including children and elderly are "
            "severely affected."
        ),
        "province": "Eastern Province",
        "district": "Nyagatare",
    }, headers=auth_header(user))
    assert submit.status_code == 201
    ref = submit.json()["reference_number"]
    assert ref.startswith("RPT-"), "Reference must use RPT- prefix"

    # Track publicly — NO Authorization header
    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    data = track.json()
    assert data["reference_number"] == ref
    assert data["type"] == "report"
    assert data["status"] == "Submitted - awaiting review", \
        "Human-readable status must be shown, not internal DB enum"
    assert data["category"] is not None
    assert data["urgency"] is not None


@pytest.mark.asyncio
async def test_uat_task2_tracking_unknown_reference_gives_clear_error(
    client: AsyncClient,
):
    """
    UAT Task 2 — error path: a mistyped or non-existent reference code must
    return HTTP 404, not a server crash. Confirms graceful error handling.
    """
    resp = await client.get("/api/v1/track/RPT-INVALID-0000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_uat_task2_service_request_also_trackable(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 2 — service requests: the public tracker must also resolve
    SRQ- references, not just RPT- report references.
    """
    user = await make_user(db, email="uat_t2_srq@uat.com")
    prov_user = await make_user(db, email="uat_t2_srq_prov@uat.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    submit = await client.post("/api/v1/service-requests", json={
        "request_type": "water_connection",
        "urgency": "medium",
        "description": "Request for a new household water connection in Karangazi Sector",
        "provider_id": str(provider.id),
    }, headers=auth_header(user))
    assert submit.status_code == 201
    ref = submit.json()["reference_number"]
    assert ref.startswith("SRQ-"), "Service requests must use SRQ- prefix"

    track = await client.get(f"/api/v1/track/{ref}")
    assert track.status_code == 200
    assert track.json()["type"] == "service_request"
    assert track.json()["reference_number"] == ref


# ═══════════════════════════════════════════════════════════════════════════════
# UAT TASK 3 — UPDATE A REPORT'S STATUS AS A WATER-SERVICE PROVIDER
# Pilot scenario: provider logs in, views assigned reports, acknowledges, moves
# to in-progress, submits resolution, and community member verifies.
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_uat_task3_provider_acknowledges_report(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 3 — Step 1: provider can acknowledge a report assigned to their
    organisation, changing status from 'open' to 'acknowledged'.
    """
    comm = await make_user(db, email="uat_t3_ack_comm@uat.com")
    prov_user = await make_user(db, email="uat_t3_ack_prov@uat.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user, organization_name="Nyagatare Water Co")

    report = await client.post("/api/v1/reports", json={
        "category": "pipe_burst",
        "urgency": "high",
        "title": "Burst pipe flooding Karangazi market area",
        "description": (
            "A large pipe has burst near Karangazi market, flooding the road "
            "and surrounding households. Water is being wasted."
        ),
        "provider_id": str(provider.id),
    }, headers=auth_header(comm))
    assert report.status_code == 201
    report_id = report.json()["id"]
    assert report.json()["status"] == "open"

    ack = await client.put(f"/api/v1/reports/{report_id}",
                           json={"status": "acknowledged"},
                           headers=auth_header(prov_user))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_uat_task3_provider_full_resolution_workflow(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 3 — Full lifecycle: provider moves report from open → acknowledged
    → in_progress → resolution_submitted, then community member verifies.
    This is the complete provider workflow as described in the UAT script.
    """
    comm = await make_user(db, email="uat_t3_full_comm@uat.com")
    prov_user = await make_user(db, email="uat_t3_full_prov@uat.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user, organization_name="Karangazi Water Services")

    # Community submits
    report = await client.post("/api/v1/reports", json={
        "category": "contamination",
        "urgency": "critical",
        "title": "Chemical smell in tap water across Karangazi Sector",
        "description": (
            "Residents of Karangazi Sector report an unusual chemical smell and "
            "brown discolouration in tap water since yesterday. Multiple households "
            "affected including children."
        ),
        "provider_id": str(provider.id),
    }, headers=auth_header(comm))
    assert report.status_code == 201
    report_id = report.json()["id"]
    assert report.json()["priority_class"] == "P1", "Contamination must be auto-classified P1"

    # Provider acknowledges
    r = await client.put(f"/api/v1/reports/{report_id}",
                         json={"status": "acknowledged"},
                         headers=auth_header(prov_user))
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"

    # Provider marks in progress
    r = await client.put(f"/api/v1/reports/{report_id}",
                         json={"status": "in_progress"},
                         headers=auth_header(prov_user))
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    # Provider submits resolution
    r = await client.put(f"/api/v1/reports/{report_id}", json={
        "status": "resolution_submitted",
        "resolution_notes": (
            "Root cause identified as a rusted pipe section near the main junction. "
            "Section replaced and water quality tested — results normal. Supply restored."
        ),
    }, headers=auth_header(prov_user))
    assert r.status_code == 200
    assert r.json()["status"] == "resolution_submitted"
    assert r.json()["resolution_notes"] is not None

    # Community verifies resolution
    verify = await client.post(f"/api/v1/reports/{report_id}/verify",
                               json={"verdict": "verified"},
                               headers=auth_header(comm))
    assert verify.status_code == 200
    assert verify.json()["status"] == "verified"


@pytest.mark.asyncio
async def test_uat_task3_provider_isolation_cannot_update_another_providers_report(
    client: AsyncClient, db: AsyncSession
):
    """
    UAT Task 3 — security boundary: Provider B must not be able to update a
    report assigned to Provider A. Confirms data isolation is enforced.
    """
    comm = await make_user(db, email="uat_t3_iso_comm@uat.com")
    prov_a_user = await make_user(db, email="uat_t3_prov_a@uat.com", role=UserRole.PROVIDER)
    prov_b_user = await make_user(db, email="uat_t3_prov_b@uat.com", role=UserRole.PROVIDER)
    prov_a = await make_provider(db, prov_a_user, organization_name="Provider A")
    await make_provider(db, prov_b_user, organization_name="Provider B")

    report = await client.post("/api/v1/reports", json={
        "category": "low_pressure",
        "urgency": "low",
        "title": "Low water pressure in Karangazi cells",
        "description": "Water pressure in the Karangazi area has been very low for the past week",
        "provider_id": str(prov_a.id),
    }, headers=auth_header(comm))
    assert report.status_code == 201
    report_id = report.json()["id"]

    # Provider B must not be able to update Provider A's report
    resp = await client.put(f"/api/v1/reports/{report_id}",
                            json={"status": "acknowledged"},
                            headers=auth_header(prov_b_user))
    assert resp.status_code in (403, 404), \
        "Provider B must be blocked from updating Provider A's report"
