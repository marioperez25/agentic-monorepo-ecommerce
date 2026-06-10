from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agentic_ecommerce_api.db import MovementReason, StoreKind

# --- write requests ---------------------------------------------------------


class InitialInventoryItem(BaseModel):
    """Used inside ``ProductCreate.initial_inventory``."""

    store_id: UUID
    quantity: int = Field(ge=0)
    reorder_threshold: int | None = Field(default=None, ge=0)


class InventorySetRequest(BaseModel):
    """``PUT /inventory/{store_id}/{product_id}`` body — set absolute qty."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"quantity": 25, "reorder_threshold": 5, "note": "monthly count"}
        }
    )

    quantity: int = Field(ge=0)
    reorder_threshold: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class InventoryMovementCreate(BaseModel):
    """``POST /inventory/{store_id}/{product_id}/movements`` body."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"delta": -2, "reason": "shrinkage", "note": "broken in transit"}
        }
    )

    delta: int = Field(
        description="Positive (restock/return) or negative (sale/shrinkage). Non-zero."
    )
    reason: MovementReason
    note: str | None = Field(default=None, max_length=500)


class InventoryLookupRequest(BaseModel):
    """``POST /inventory/lookup`` body — batch read of one store's stock for
    many products in a single round trip. The cap matches our pagination
    cap (100) to keep response shapes predictable."""

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


class InventoryLookupItem(BaseModel):
    """One entry of an ``/inventory/lookup`` response. ``present`` lets
    admin clients distinguish 'we have a row that says 0' from 'no row at
    all'; storefronts can ignore it."""

    product_id: UUID
    quantity: int
    reorder_threshold: int | None
    present: bool


class InventoryLookupResponse(BaseModel):
    store_id: UUID
    items: list[InventoryLookupItem]


# --- read responses ---------------------------------------------------------


class InventoryRowResponse(BaseModel):
    """Single-pair snapshot (``GET /inventory/{store_id}/{product_id}``)."""

    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    store_id: UUID
    quantity: int
    reorder_threshold: int | None
    updated_at: datetime
    updated_by: UUID


class StoreInventoryRow(BaseModel):
    """One row of ``GET /stores/{id}/inventory`` — flattened with product info
    so clients don't N+1 to the products endpoint."""

    product_id: UUID
    product_name: str
    product_sku: str | None
    quantity: int
    reorder_threshold: int | None
    updated_at: datetime


class _StoreBlock(BaseModel):
    id: UUID
    name: str
    kind: StoreKind


class StoreInventoryListResponse(BaseModel):
    store: _StoreBlock
    items: list[StoreInventoryRow]
    total: int
    page: int
    limit: int
    total_pages: int


class ProductInventoryRow(BaseModel):
    """One row of ``GET /products/{id}/inventory`` — flattened with store info."""

    store_id: UUID
    store_name: str
    store_kind: StoreKind
    quantity: int
    reorder_threshold: int | None
    updated_at: datetime


class _ProductBlock(BaseModel):
    id: UUID
    name: str
    sku: str | None


class ProductInventoryListResponse(BaseModel):
    product: _ProductBlock
    items: list[ProductInventoryRow]
    total: int
    page: int
    limit: int
    total_pages: int


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    store_id: UUID
    delta: int
    reason: MovementReason
    quantity_after: int
    note: str | None
    created_by: UUID
    created_at: datetime
