"""Global exception handler.

Catches anything an endpoint raises that isn't already a ``HTTPException``
or a Pydantic ``RequestValidationError`` (FastAPI handles those itself).
The handler logs the full traceback at ``ERROR`` level and returns a
generic 500 — **never** leaking the exception type, message, or stack
to the client.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("agentic_ecommerce_api.unhandled")


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Generate a short correlation id so a user can quote it when filing a
    # bug and we can grep the server logs for the matching traceback.
    incident_id = uuid.uuid4().hex[:12]
    log.error(
        "Unhandled exception (incident=%s) at %s %s",
        incident_id,
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "incident_id": incident_id},
    )


def install(app: FastAPI) -> None:
    """Register the catch-all handler on the given FastAPI app."""
    app.add_exception_handler(Exception, _unhandled_exception_handler)
