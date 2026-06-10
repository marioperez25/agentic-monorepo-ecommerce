"""Smoke tests that lock down the auto-generated API documentation."""

from __future__ import annotations

from httpx import AsyncClient


async def test_swagger_ui_is_served(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


async def test_redoc_is_served(client: AsyncClient) -> None:
    response = await client.get("/redoc")
    assert response.status_code == 200
    assert "redoc" in response.text.lower()


async def test_openapi_spec_has_expected_shape(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    assert spec["info"]["title"] == "Agentic Driven E-Commerce API"
    assert spec["info"]["version"] == "0.1.0"

    paths = spec["paths"]
    assert "/health" in paths
    assert "/auth/login" in paths
    assert "/auth/me" in paths


async def test_openapi_registers_bearer_security_scheme(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    schemes = spec["components"]["securitySchemes"]
    # FastAPI names the scheme after the dependency's class — HTTPBearer.
    bearer = next(s for s in schemes.values() if s.get("scheme", "").lower() == "bearer")
    assert bearer["type"] == "http"


async def test_protected_route_advertises_security(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    me_op = spec["paths"]["/auth/me"]["get"]
    assert me_op["security"], "GET /auth/me should require a security scheme"
    assert "401" in me_op["responses"]
