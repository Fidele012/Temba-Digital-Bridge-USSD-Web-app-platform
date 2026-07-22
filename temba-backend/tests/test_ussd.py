"""
USSD callback endpoint tests — Africa's Talking integration testing.
Covers: welcome screen, language selection, registration, login, PIN,
report submission, appointment booking, service requests, tracking, exit.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_user, make_provider
from app.models.user import UserRole
from app.core.security import hash_password

USSD = "/api/v1/ussd/callback"


def _post(client, phone, text, session="sess-test"):
    return client.post(USSD, data={
        "sessionId": session,
        "serviceCode": "*384*36640#",
        "phoneNumber": phone,
        "text": text,
    })


# ── Welcome & Language Selection ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_welcome_screen(client: AsyncClient):
    resp = await _post(client, "+250780000001", "")
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "Temba" in resp.text


@pytest.mark.asyncio
async def test_ussd_language_selection_english(client: AsyncClient):
    resp = await _post(client, "+250780000002", "1")
    assert resp.status_code == 200
    assert "Register" in resp.text or "Login" in resp.text


@pytest.mark.asyncio
async def test_ussd_language_selection_kinyarwanda(client: AsyncClient):
    resp = await _post(client, "+250780000003", "2")
    assert resp.status_code == 200
    assert "Iyandikishe" in resp.text or "Injira" in resp.text


# ── Exit ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_exit_command(client: AsyncClient):
    resp = await _post(client, "+250780000006", "1*0")
    assert resp.status_code == 200
    assert "END" in resp.text


# ── Login — Unregistered & Wrong PIN ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_unregistered_number(client: AsyncClient):
    resp = await _post(client, "+250780999999", "1*2")
    assert resp.status_code == 200
    body = resp.text
    assert "CON" in body or "END" in body


@pytest.mark.asyncio
async def test_ussd_login_wrong_pin(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_pin@test.com", phone="+250780000004",
                    ussd_pin_hash=hash_password("1234"))
    resp = await _post(client, "+250780000004", "1*2*9999")
    assert resp.status_code == 200
    assert "END" in resp.text


# ── Login — Correct PIN → Main Menu ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_login_shows_main_menu(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_menu@test.com", phone="+250780100001",
                    ussd_pin_hash=hash_password("4321"))
    resp = await _post(client, "+250780100001", "1*2*4321")
    assert resp.status_code == 200
    body = resp.text
    assert "CON" in body
    assert "Report" in body or "Tanga" in body


# ── Report Water Issue (Menu 1) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_report_category_menu(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_rpt@test.com", phone="+250780200001",
                    ussd_pin_hash=hash_password("1111"))
    resp = await _post(client, "+250780200001", "1*2*1111*1")
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "Contamination" in resp.text or "Amazi yanduye" in resp.text


@pytest.mark.asyncio
async def test_ussd_report_full_flow(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="ussd_rpt_full@test.com", phone="+250780200002",
                           ussd_pin_hash=hash_password("1111"), province="Kigali City",
                           district="Nyarugenge")
    prov_user = await make_user(db, email="ussd_prov@test.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # 1*2*1111 = EN + Login + PIN
    # *1 = Report water issue
    # *1 = Category: Contamination
    # *1 = Urgency: High
    # *1 = Provider: first in list → submits report directly
    resp = await _post(client, "+250780200002", "1*2*1111*1*1*1*1")
    assert resp.status_code == 200
    assert "END" in resp.text
    assert "RPT-" in resp.text


# ── Track Reports (Menu 2) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_track_no_reports(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_track@test.com", phone="+250780300001",
                    ussd_pin_hash=hash_password("2222"))
    resp = await _post(client, "+250780300001", "1*2*2222*2")
    assert resp.status_code == 200
    assert "END" in resp.text
    assert "no report" in resp.text.lower() or "nta raporo" in resp.text.lower()


# ── Book Appointment (Menu 3) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_appointment_reason_menu(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="ussd_appt@test.com", phone="+250780400001",
                           ussd_pin_hash=hash_password("3333"))
    prov_user = await make_user(db, email="ussd_appt_prov@test.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # 1*2*3333 = EN + Login + PIN
    # *3 = Book appointment → show provider list
    # *1 = Select first provider → show reason list
    resp = await _post(client, "+250780400001", "1*2*3333*3*1")
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "connection" in resp.text.lower() or "Gutuza" in resp.text


@pytest.mark.asyncio
async def test_ussd_appointment_full_flow(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="ussd_appt_full@test.com", phone="+250780400002",
                           ussd_pin_hash=hash_password("3333"))
    prov_user = await make_user(db, email="ussd_appt_prov2@test.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # 1*2*3333*3 = EN + Login + PIN + Book appointment
    # *1 = Provider 1
    # *1 = Reason: New connection
    # *1 = Date: Tomorrow
    # *1 = Time: 08:00-09:00
    # → confirmation screen
    resp = await _post(client, "+250780400002", "1*2*3333*3*1*1*1*1")
    assert resp.status_code == 200
    assert "CON" in resp.text

    # *1 = Confirm
    resp = await _post(client, "+250780400002", "1*2*3333*3*1*1*1*1*1")
    assert resp.status_code == 200
    assert "END" in resp.text
    assert "booked" in resp.text.lower() or "requested" in resp.text.lower() or "Randevu" in resp.text


# ── My Appointments (Menu 4) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_my_appointments_empty(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_myappt@test.com", phone="+250780500001",
                    ussd_pin_hash=hash_password("4444"))
    resp = await _post(client, "+250780500001", "1*2*4444*4")
    assert resp.status_code == 200
    assert "END" in resp.text


# ── Service Request Status (Menu 5) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_service_request_status_empty(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_svc@test.com", phone="+250780600001",
                    ussd_pin_hash=hash_password("5555"))
    resp = await _post(client, "+250780600001", "1*2*5555*5")
    assert resp.status_code == 200
    assert "END" in resp.text


# ── Submit Service Request (Menu 6) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_service_request_type_menu(client: AsyncClient, db: AsyncSession):
    await make_user(db, email="ussd_sr@test.com", phone="+250780700001",
                    ussd_pin_hash=hash_password("6666"))
    resp = await _post(client, "+250780700001", "1*2*6666*6")
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "water connection" in resp.text.lower() or "Gutuza" in resp.text.lower()


@pytest.mark.asyncio
async def test_ussd_service_request_full_flow(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="ussd_sr_full@test.com", phone="+250780700002",
                           ussd_pin_hash=hash_password("6666"), province="Kigali City")
    prov_user = await make_user(db, email="ussd_sr_prov@test.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # 1*2*6666*6 = EN + Login + PIN + Submit service request
    # *1 = Water connection
    # *1 = Provider 1
    # *1 = Urgency: High → submits service request directly
    resp = await _post(client, "+250780700002", "1*2*6666*6*1*1*1")
    assert resp.status_code == 200
    assert "END" in resp.text
    assert "SRQ-" in resp.text


# ── Kinyarwanda Full Flow ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_kinyarwanda_report_flow(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="ussd_rw@test.com", phone="+250780800001",
                           ussd_pin_hash=hash_password("7777"), province="Kigali City")
    prov_user = await make_user(db, email="ussd_rw_prov@test.com", role=UserRole.PROVIDER)
    await make_provider(db, prov_user)

    # 2 = Kinyarwanda, *2 = Login, *7777 = PIN, *1 = Report
    resp = await _post(client, "+250780800001", "2*2*7777*1")
    assert resp.status_code == 200
    assert "CON" in resp.text

    # *1*1*1 = Category + Urgency + Provider → submits report directly
    resp = await _post(client, "+250780800001", "2*2*7777*1*1*1*1")
    assert resp.status_code == 200
    assert "END" in resp.text
    assert "RPT-" in resp.text


# ── Registration Flow ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ussd_registration_enter_name(client: AsyncClient):
    # 1 = English, 1 = Register → ask for name
    resp = await _post(client, "+250780900001", "1*1")
    assert resp.status_code == 200
    assert "CON" in resp.text
    assert "name" in resp.text.lower() or "amazina" in resp.text.lower()
