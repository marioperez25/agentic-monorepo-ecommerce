from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentic_ecommerce_api.inventory import InitialInventoryItem


class ProductCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Cold Brew Concentrate",
                "description": "32oz, makes 16 servings.",
                "price_cents": 1499,
                "currency": "USD",
                "sku": "CB-32-001",
                "slug": None,
            }
        }
    )

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    price_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217 code, e.g. USD.")
    sku: str | None = Field(default=None, max_length=64)
    slug: str | None = Field(
        default=None,
        max_length=220,
        description="Optional. If omitted, generated from `name`.",
    )
    initial_inventory: list[InitialInventoryItem] = Field(
        default_factory=list,
        description=(
            "Optional initial stock per store. Each entry creates an inventory "
            "row and an `initial` movement in the same transaction."
        ),
    )


class ProductUpdate(BaseModel):
    """All fields optional — PATCH semantics. Only set fields are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    sku: str | None = Field(default=None, max_length=64)
    slug: str | None = Field(default=None, max_length=220)
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    price_cents: int
    currency: str
    sku: str | None
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
