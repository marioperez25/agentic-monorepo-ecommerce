from httpx import AsyncClient


async def test_health_endpoint_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_openapi_lists_auth_login(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    spec = response.json()
    assert "/auth/login" in spec["paths"]
