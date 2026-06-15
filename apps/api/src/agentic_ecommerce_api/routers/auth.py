from __future__ import annotations

from typing import Annotated

from agentic_ecommerce_shared import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api._rate_limit import limiter
from agentic_ecommerce_api.auth import (
    CurrentUser,
    LoginRequest,
    TokenResponse,
    UserResponse,
    create_access_token,
    verify_password,
)
from agentic_ecommerce_api.db import User, get_session

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


_INVALID_CREDENTIALS_RESPONSE = {
    "description": "Invalid username or password.",
    "content": {
        "application/json": {
            "example": {"detail": "Invalid username or password"},
        }
    },
}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange credentials for a JWT",
    description=(
        "POST a username and password. On success, returns a signed bearer "
        "token that is valid for `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` "
        "(default 60min). Rate-limited per IP (see `RATE_LIMIT_LOGIN`)."
    ),
    response_description="A signed JWT and its expiry.",
    responses={
        401: _INVALID_CREDENTIALS_RESPONSE,
        429: {"description": "Too many requests, slow down."},
    },
)
@limiter.limit(lambda: get_settings().rate_limit_login)
async def login(request: Request, payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = (
        await session.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()

    # Always run a verify, even on a missing user, to avoid leaking which
    # accounts exist via response-time differences.
    candidate_hash = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(payload.password, candidate_hash)

    if user is None or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=user.id, username=user.username)
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().jwt_access_token_expire_minutes * 60,
    )


# Pre-computed bcrypt hash of an empty string. Used only as a constant-time
# decoy when the requested username does not exist.
_DUMMY_HASH = "$2b$12$CwTycUXWue0Thq9StjUM0uJ8eVXr6V3GqLZRfL2nDmaGvKfQpQqUW"


_NOT_AUTHENTICATED_RESPONSE = {
    "description": "Missing, malformed, expired, or revoked bearer token.",
    "content": {
        "application/json": {
            "example": {"detail": "Not authenticated"},
        }
    },
}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user",
    description=(
        "Returns the user associated with the bearer token in the "
        "`Authorization` header. Use the **Authorize** button in Swagger "
        "UI to attach a token."
    ),
    response_description="Public profile of the authenticated user.",
    responses={401: _NOT_AUTHENTICATED_RESPONSE},
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
