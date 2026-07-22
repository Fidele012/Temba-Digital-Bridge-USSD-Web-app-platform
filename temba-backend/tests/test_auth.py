"""Authentication endpoint tests."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, make_user
from app.models.user import UserRole


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db: AsyncSession):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "newuser@test.com",
        "phone": "+250780000101",
        "password": "Test@12345",
        "full_name": "New User",
        "role": "community",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.com"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="dup@test.com")
    resp = await client.post("/api/v1/auth/register", json={
        "email": "dup@test.com",
        "phone": "+250780000102",
        "password": "Test@12345",
        "full_name": "Dup User",
        "role": "community",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="login@test.com")
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com",
        "password": "Test@12345",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="wrongpw@test.com")
    resp = await client.post("/api/v1/auth/login", json={
        "email": "wrongpw@test.com",
        "password": "WrongPass@1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="me@test.com")
    resp = await client.get("/api/v1/users/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, db: AsyncSession):
    user = await make_user(db, email="changepw@test.com")
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Test@12345", "new_password": "NewPass@99"},
        headers=auth_header(user),
    )
    assert resp.status_code == 200
