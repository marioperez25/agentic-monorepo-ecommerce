"""Public-facing schemas for the storefront API.

These responses deliberately omit exact quantity and `reorder_threshold` —
both are internal competitive information that shouldn't leak to guests.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityBucket(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


def coarsen(quantity: int | None, reorder_threshold: int | None) -> AvailabilityBucket:
    """Reduce a (quantity, threshold) pair to a public-safe bucket.

    Rules:
    - no row, or quantity 0          → OUT_OF_STOCK
    - quantity <= threshold (set)    → LOW_STOCK
    - otherwise                      → IN_STOCK
    """
    if quantity is None or quantity <= 0:
        return AvailabilityBucket.OUT_OF_STOCK
    if reorder_threshold is not None and quantity <= reorder_threshold:
        return AvailabilityBucket.LOW_STOCK
    return AvailabilityBucket.IN_STOCK


class StorefrontSingleResponse(BaseModel):
    """``GET /storefront/inventory/{store_id}/{product_id}``."""

    store_id: UUID
    product_id: UUID
    availability: AvailabilityBucket


class StorefrontAvailability(BaseModel):
    """One entry in the batch response."""

    product_id: UUID
    availability: AvailabilityBucket


class StorefrontLookupRequest(BaseModel):
    """``POST /storefront/inventory/lookup`` body. Mirrors the authenticated
    batch shape but the response is coarsened."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "store_id": "11111111-1111-1111-1111-111111111111",
                "product_ids": [
                    "22222222-2222-2222-2222-222222222222",
                    "33333333-3333-3333-3333-333333333333",
                ],
            }
        }
    )

    store_id: UUID
    product_ids: list[UUID] = Field(min_length=1, max_length=100)


class StorefrontLookupResponse(BaseModel):
    store_id: UUID
    items: list[StorefrontAvailability]
