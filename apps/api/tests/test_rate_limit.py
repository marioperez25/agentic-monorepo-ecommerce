"""Rate limiting on /auth/login.

The rest of the suite disables the limiter (see conftest). These tests
flip the master switch back on, hammer the endpoint, and assert that
slowapi starts returning 429.
"""

from __future__ import annotations

import pytest
from agentic_ecommerce_api._rate_limit import limiter
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def enable_limiter() -> None:
    """Force the limiter on for this module + reset its in-memory storage
    so per-IP counters from earlier tests don't bleed in."""
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.enabled = False
    limiter.reset()


async def test_login_returns_429_after_threshold(client: AsyncClient) -> None:
    # The default config is "5/minute". After 5 attempts from the same IP,
    # the 6th should be 429 regardless of credentials.
    payload = {"username": "ghost", "password": "anything"}
    for _ in range(5):
        r = await client.post("/auth/login", json=payload)
        # Each within-limit attempt against an unknown user → 401.
        assert r.status_code == 401, r.text

    r = await client.post("/auth/login", json=payload)
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many requests, slow down."
