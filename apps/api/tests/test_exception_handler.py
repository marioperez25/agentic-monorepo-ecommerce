"""The catch-all 500 handler must scrub tracebacks and never leak the
exception type or message to the client."""

from __future__ import annotations

import logging

import pytest
from agentic_ecommerce_api import _exception_handler
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def boom_app() -> FastAPI:
    """Tiny app that just raises — used to exercise the handler in isolation."""
    app = FastAPI()
    _exception_handler.install(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("super secret traceback that must NOT leak")

    return app


async def test_unhandled_exception_returns_generic_500(boom_app: FastAPI) -> None:
    transport = ASGITransport(app=boom_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "incident_id" in body
    # The internal message + exception type must NEVER appear in the response.
    text = r.text
    assert "super secret traceback" not in text
    assert "RuntimeError" not in text


async def test_handler_logs_traceback_with_incident_id(
    boom_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    transport = ASGITransport(app=boom_app, raise_app_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="agentic_ecommerce_api.unhandled"):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/boom")

    incident_id = r.json()["incident_id"]
    matching = [rec for rec in caplog.records if incident_id in rec.getMessage()]
    assert matching, "expected a log record carrying the incident_id"
    # The full traceback should be present in the server-side log.
    record = matching[0]
    assert record.exc_info is not None, "expected exc_info on the log record"
