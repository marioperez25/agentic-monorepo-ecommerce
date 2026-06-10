"""Public (no-auth) storefront endpoints.

These are the *only* endpoints in the API that don't require a bearer token.
Keep the response surface minimal — coarsened availability buckets, never
exact quantities or thresholds. New public endpoints should live here so the
audit trail of what's exposed to the world stays in one file.

Only ONLINE stores are publicly addressable. Requests for PHYSICAL or
MARKETPLACE store ids return 404 (same shape as "not found") so we don't
even confirm those store ids exist to anonymous callers.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api.db import Inventory, Store, StoreKind, get_session
from agentic_ecommerce_api.storefront import (
    StorefrontAvailability,
    StorefrontLookupRequest,
    StorefrontLookupResponse,
    StorefrontSingleResponse,
    coarsen,
)

router = APIRouter(prefix="/storefront", tags=["storefront"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def _require_public_store(session: AsyncSession, store_id: UUID) -> Store:
    """Resolve a store id, but only if it's an active ONLINE store.

    Returns the same 404 for "doesn't exist", "inactive", and "wrong kind" so
    the response shape doesn't leak the existence of internal stores.
    """
    store = (await session.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if store is None or not store.is_active or store.kind != StoreKind.ONLINE:
        raise _NOT_FOUND
    return store


@router.get(
    "/inventory/{store_id}/{product_id}",
    response_model=StorefrontSingleResponse,
    summary="Public availability for one (store, product) pair",
    description=(
        "Returns a coarsened availability bucket — `in_stock`, `low_stock`, "
        "or `out_of_stock`. Exact quantity and reorder threshold are "
        "intentionally not exposed. Only ONLINE stores are addressable."
    ),
    responses={404: {"description": "Store is not a public storefront, or not found."}},
)
async def storefront_inventory_single(
    store_id: UUID,
    product_id: UUID,
    session: SessionDep,
) -> StorefrontSingleResponse:
    await _require_public_store(session, store_id)
    row = (
        await session.execute(
            select(Inventory).where(
                Inventory.store_id == store_id,
                Inventory.product_id == product_id,
            )
        )
    ).scalar_one_or_none()

    qty = row.quantity if row else None
    threshold = row.reorder_threshold if row else None
    return StorefrontSingleResponse(
        store_id=store_id,
        product_id=product_id,
        availability=coarsen(qty, threshold),
    )


@router.post(
    "/inventory/lookup",
    response_model=StorefrontLookupResponse,
    summary="Public batch availability lookup",
    description=(
        "Same shape as the authenticated `/inventory/lookup`, but returns "
        "coarsened availability buckets instead of exact stock. Only ONLINE "
        "stores are addressable."
    ),
    responses={404: {"description": "Store is not a public storefront, or not found."}},
)
async def storefront_inventory_lookup(
    payload: StorefrontLookupRequest,
    session: SessionDep,
) -> StorefrontLookupResponse:
    await _require_public_store(session, payload.store_id)

    # De-dupe but preserve order so the response keeps the client's order.
    seen: set[UUID] = set()
    unique_ids: list[UUID] = []
    for pid in payload.product_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)

    rows = (
        (
            await session.execute(
                select(Inventory).where(
                    Inventory.store_id == payload.store_id,
                    Inventory.product_id.in_(unique_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    by_pid = {r.product_id: r for r in rows}

    items = [
        StorefrontAvailability(
            product_id=pid,
            availability=coarsen(
                by_pid[pid].quantity if pid in by_pid else None,
                by_pid[pid].reorder_threshold if pid in by_pid else None,
            ),
        )
        for pid in unique_ids
    ]
    return StorefrontLookupResponse(store_id=payload.store_id, items=items)
