from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentic_ecommerce_api.db import StoreKind


class StoreCreate(BaseModel):
    """Single create schema for all kinds; the router enforces kind-specific
    required fields (and the DB enforces them again via CHECK constraints).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kind": "physical",
                "name": "Downtown POS",
                "currency": "MXN",
                "timezone": "America/Mexico_City",
                "address_line1": "Av. Reforma 100",
                "city": "Ciudad de Mexico",
                "country": "MX",
            }
        }
    )

    kind: StoreKind
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    description: str | None = Field(default=None, max_length=10_000)
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217.")
    timezone: str = Field(min_length=1, max_length=64, description="IANA tz name.")

    # physical
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=255)

    # online
    domain: str | None = Field(default=None, max_length=255)

    # marketplace — ADMIN may set this; for VENDOR/CUSTOMER callers the
    # router overrides it with the caller's user id.
    owner_user_id: UUID | None = None


class StoreUpdate(BaseModel):
    """All fields optional — PATCH semantics. `kind` and `owner_user_id` are
    intentionally not editable (changing kind would require revalidating
    every nullable field; transfer of marketplace ownership is a separate
    flow worth modeling explicitly later)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    description: str | None = Field(default=None, max_length=10_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None

    # physical
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=255)

    # online
    domain: str | None = Field(default=None, max_length=255)


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: StoreKind
    name: str
    slug: str
    description: str | None
    currency: str
    timezone: str
    is_active: bool

    address_line1: str | None
    address_line2: str | None
    city: str | None
    region: str | None
    country: str | None
    postal_code: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    phone: str | None
    contact_email: str | None

    domain: str | None
    owner_user_id: UUID | None

    created_by: UUID
    created_at: datetime
    updated_at: datetime
