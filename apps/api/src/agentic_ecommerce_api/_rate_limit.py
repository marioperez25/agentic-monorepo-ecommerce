"""In-process rate limiter (slowapi).

Wraps slowapi's `Limiter` so the rest of the codebase imports a single
symbol. The limiter is keyed by client IP via `get_remote_address` and
toggled by `Settings.rate_limit_enabled` so the test suite can run many
requests against the same loopback IP without hitting limits.

To rate-limit a route:

    from agentic_ecommerce_api._rate_limit import limiter
    from agentic_ecommerce_shared import get_settings

    @router.post(...)
    @limiter.limit(lambda: get_settings().rate_limit_login)
    async def login(request: Request, ...): ...

The `request: Request` parameter is required by slowapi to extract the
key — every limited endpoint must declare it.
"""

from __future__ import annotations

from agentic_ecommerce_shared import get_settings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def _limiter_enabled() -> bool:
    return get_settings().rate_limit_enabled


limiter = Limiter(key_func=get_remote_address, enabled=_limiter_enabled())


async def _on_rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler so the response is JSON-shaped like the rest of the
    API instead of slowapi's default text body."""
    # Delegate to slowapi's handler to get the headers (Retry-After etc.),
    # then re-shape the body.
    base = _rate_limit_exceeded_handler(request, exc)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests, slow down."},
        headers=dict(base.headers),
    )


def install(app: FastAPI) -> None:
    """Wire the limiter + middleware + 429 handler onto a FastAPI app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _on_rate_limit_exceeded)
