from __future__ import annotations

from uuid import UUID

import pytest
from agentic_ecommerce_api.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from agentic_ecommerce_api.auth.jwt import InvalidTokenError
from agentic_ecommerce_api.db import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# --- password unit tests -----------------------------------------------------


def test_hash_password_produces_a_different_string() -> None:
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert h.startswith("$2b$")


def test_verify_password_accepts_correct_password() -> None:
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_rejects_wrong_password() -> None:
    h = hash_password("hunter2")
    assert verify_password("not-it", h) is False


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# --- jwt unit tests ----------------------------------------------------------


def test_token_roundtrip() -> None:
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    token = create_access_token(subject=user_id, username="alice")
    decoded = decode_access_token(token)
    assert decoded["sub"] == str(user_id)
    assert decoded["username"] == "alice"
    assert "exp" in decoded
    assert "iat" in decoded


def test_decode_rejects_tampered_token() -> None:
    token = create_access_token(subject=UUID(int=0), username="alice")
    # Flip a character in the payload section to break the signature.
    parts = token.split(".")
    tampered = ".".join([parts[0], parts[1][:-1] + ("a" if parts[1][-1] != "a" else "b"), parts[2]])
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


# --- /auth/login integration -------------------------------------------------


async def test_login_success_returns_valid_token(client: AsyncClient, alice: User) -> None:
    response = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "correct-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    decoded = decode_access_token(body["access_token"])
    assert decoded["username"] == "alice"
    assert decoded["sub"] == str(alice.id)


async def test_login_wrong_password_returns_401(client: AsyncClient, alice: User) -> None:
    response = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert response.status_code == 401


async def test_login_rejects_empty_fields(client: AsyncClient) -> None:
    response = await client.post("/auth/login", json={"username": "", "password": ""})
    assert response.status_code == 422


# --- GET /auth/me (protected) -----------------------------------------------


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_me_returns_current_user(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["id"] == str(alice.id)
    assert body["role"] == "admin"
    assert "password_hash" not in body


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_me_with_wrong_scheme_returns_401(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    response = await client.get("/auth/me", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


async def test_me_with_token_for_deleted_user_returns_401(
    client: AsyncClient, alice: User, db_session: AsyncSession
) -> None:
    token = await _login(client, "alice", "correct-password")
    await db_session.delete(alice)
    await db_session.commit()

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
