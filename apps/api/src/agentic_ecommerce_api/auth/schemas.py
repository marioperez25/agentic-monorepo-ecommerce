from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentic_ecommerce_api.db import Role


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "alice", "password": "s3cret"},
        }
    )

    username: str = Field(min_length=1, max_length=64, description="Unique username.")
    password: str = Field(min_length=1, max_length=256, description="Plaintext password.")


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }
    )

    access_token: str = Field(description="Signed JWT access token.")
    token_type: str = Field(default="bearer", description="Always `bearer`.")
    expires_in: int = Field(description="Token lifetime in seconds.")


class UserResponse(BaseModel):
    """Public view of a User row. Excludes ``password_hash`` deliberately."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "12345678-1234-5678-1234-567812345678",
                "username": "alice",
                "role": "admin",
            }
        },
    )

    id: UUID
    username: str
    role: Role
