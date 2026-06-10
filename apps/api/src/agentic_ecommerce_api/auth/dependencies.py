"""FastAPI dependencies for authenticated routes.

- ``get_current_user`` — extracts a bearer token, decodes it, loads the user.
  Any failure path returns 401 with a generic message — we don't tell the
  caller *why* their token is bad.
- ``optional_current_user`` — returns ``None`` if no token is supplied (used
  for endpoints that allow guests). A *malformed* token is still rejected
  with 401, on the principle that "I tried and failed" isn't the same as
  "I never tried."
- ``require_roles(*roles)`` — dependency factory that returns 403 when the
  authenticated user's ``role`` is not in the allowed set.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api.auth.jwt import InvalidTokenError, decode_access_token
from agentic_ecommerce_api.db import Role, User, get_session

# auto_error=False lets us return 401 (not 403) when the header is missing.
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient role",
)


async def _resolve_user(
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _UNAUTHORIZED from exc

    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise _UNAUTHORIZED
    try:
        user_id = UUID(raw_sub)
    except ValueError as exc:
        raise _UNAUTHORIZED from exc

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise _UNAUTHORIZED
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    return await _resolve_user(credentials, session)


async def optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    if credentials is None:
        return None
    return await _resolve_user(credentials, session)


def require_roles(*allowed: Role) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: only callers whose ``role`` is in ``allowed`` pass."""

    async def _enforce(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed:
            raise _FORBIDDEN
        return current_user

    return _enforce


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(optional_current_user)]
RequireAdmin = Annotated[User, Depends(require_roles(Role.ADMIN))]
RequireSellerOrAdmin = Annotated[User, Depends(require_roles(Role.ADMIN, Role.SELLER))]
