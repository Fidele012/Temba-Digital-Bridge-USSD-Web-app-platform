"""Service Request lifecycle tests — integration testing strategy."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_provider, make_user
from app.models.user import UserRole

_SR_PAYLOAD = {
    "request_type": "water_connection",
    "urgency": "high",
    "description": "Need a new water connection installed at home",
    "province": "Kigali City",
    "district": "Gasabo",
}


@pytest.mark.asyncio
async def test_create_service_request(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="sr_create@test.com")
    resp = await client.post("/api/v1/service-requests", json=_SR_PAYLOAD, headers=auth_header(user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["request_type"] == "water_connection"
    assert data["status"] == "submitted"


@pytest.mark.asyncio
async def test_list_own_service_requests(client: AsyncClient, db: AsyncSession):
    u1 = await make_user(db, email="sr_u1@test.com")
    u2 = await make_user(db, email="sr_u2@test.com")
    await client.post("/api/v1/service-requests", json=_SR_PAYLOAD, headers=auth_header(u1))
    await client.post("/api/v1/service-requests", json=_SR_PAYLOAD | {"description": "Different request for water"}, headers=auth_header(u2))

    resp = await client.get("/api/v1/service-requests", headers=auth_header(u1))
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["user_id"] == str(u1.id)


@pytest.mark.asyncio
async def test_provider_updates_service_request(client: AsyncClient, db: AsyncSession):
    community = await make_user(db, email="sr_comm@test.com")
    prov_user = await make_user(db, email="sr_prov@test.com", role=UserRole.PROVIDER)
    provider = await make_provider(db, prov_user)

    create_resp = await client.post(
        "/api/v1/service-requests",
        json=_SR_PAYLOAD | {"provider_id": str(provider.id)},
        headers=auth_header(community),
    )
    sr_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/service-requests/{sr_id}",
        json={"status": "acknowledged"},
        headers=auth_header(prov_user),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"
