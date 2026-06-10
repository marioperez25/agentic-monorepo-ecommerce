"""JWT issuance and verification.

Tokens carry the user id as ``sub``, plus standard ``iat`` and ``exp``
claims. Signing key, algorithm, and expiry come from ``Settings`` so they
can be rotated via env without code changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from agentic_ecommerce_shared import get_settings


class InvalidTokenError(Exception):
    """Raised when a token is malformed, expired, or has an invalid signature."""


def create_access_token(*, subject: UUID, username: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
