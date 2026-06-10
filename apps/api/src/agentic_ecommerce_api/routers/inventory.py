"""Inventory CRUD and audit-log endpoints.

Writes are ADMIN-only for now. Reads require any authenticated user.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api._pagination import Page, PageParamsDep, paginate
from agentic_ecommerce_api.auth import CurrentUser, RequireAdmin
from agentic_ecommerce_api.db import (
    Inventory,
    InventoryMovement,
    Product,
    Store,
    get_session,
)
from agentic_ecommerce_api.inventory import (
    InventoryLookupItem,
    InventoryLookupRequest,
    InventoryLookupResponse,
    InventoryMovementCreate,
    InventoryMovementResponse,
    InventoryRowResponse,
    InventorySetRequest,
    ProductInventoryListResponse,
    ProductInventoryRow,
    StoreInventoryListResponse,
    StoreInventoryRow,
)
from agentic_ecommerce_api.inventory.service import (
    InsufficientStockError,
    InventoryError,
    apply_movement,
    set_absolute_quantity,
)

router = APIRouter(tags=["inventory"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _page_meta(total: int, page: int, limit: int) -> dict[str, int]:
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
    }


async def _require_product(session: AsyncSession, product_id: UUID) -> Product:
    p = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if p is None or not p.is_active:
        raise _NOT_FOUND
    return p


async def _require_store(session: AsyncSession, store_id: UUID) -> Store:
    s = (await session.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if s is None or not s.is_active:
        raise _NOT_FOUND
    return s


# --- batch lookup (one store, many products) -------------------------------


@router.post(
    "/inventory/lookup",
    response_model=InventoryLookupResponse,
    summary="Batch read stock for one store across many products",
    description=(
        "Use this on category/search pages to avoid N+1 inventory calls. "
        "Each entry of `product_ids` is returned in the response — products "
        "with no inventory row come back as `quantity=0, present=false` so "
        "storefronts can render 'Out of stock' uniformly."
    ),
    responses={404: {"description": "Store not found or inactive."}},
)
async def lookup_inventory(
    payload: InventoryLookupRequest,
    session: SessionDep,
    _current_user: CurrentUser,
) -> InventoryLookupResponse:
    await _require_store(session, payload.store_id)

    # De-dupe while preserving order so the response keeps the client's order.
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
        InventoryLookupItem(
            product_id=pid,
            quantity=by_pid[pid].quantity if pid in by_pid else 0,
            reorder_threshold=by_pid[pid].reorder_threshold if pid in by_pid else None,
            present=pid in by_pid,
        )
        for pid in unique_ids
    ]
    return InventoryLookupResponse(store_id=payload.store_id, items=items)


# --- single-pair snapshot ---------------------------------------------------


@router.get(
    "/inventory/{store_id}/{product_id}",
    response_model=InventoryRowResponse,
    summary="Get current stock for one (store, product) pair",
)
async def get_inventory_row(
    store_id: UUID,
    product_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
) -> Inventory:
    row = (
        await session.execute(
            select(Inventory).where(
                Inventory.store_id == store_id,
                Inventory.product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


# --- single-pair write: set absolute quantity -------------------------------


@router.put(
    "/inventory/{store_id}/{product_id}",
    response_model=InventoryRowResponse,
    summary="Set absolute stock for one (store, product) pair (ADMIN only)",
    responses={
        404: {"description": "Store or product not found / inactive."},
        422: {"description": "quantity must be >= 0."},
    },
)
async def set_inventory(
    store_id: UUID,
    product_id: UUID,
    payload: InventorySetRequest,
    session: SessionDep,
    current_user: RequireAdmin,
) -> Inventory:
    await _require_store(session, store_id)
    await _require_product(session, product_id)
    try:
        row = await set_absolute_quantity(
            session,
            product_id=product_id,
            store_id=store_id,
            new_quantity=payload.quantity,
            actor_user_id=current_user.id,
            note=payload.note,
            reorder_threshold=payload.reorder_threshold,
        )
    except InventoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    await session.refresh(row)
    return row


# --- single-pair write: apply delta movement --------------------------------


@router.post(
    "/inventory/{store_id}/{product_id}/movements",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply a stock movement (ADMIN only)",
    responses={
        404: {"description": "Store or product not found / inactive."},
        409: {"description": "Movement would leave stock negative."},
        422: {"description": "Invalid delta (e.g. zero) or other domain error."},
    },
)
async def post_movement(
    store_id: UUID,
    product_id: UUID,
    payload: InventoryMovementCreate,
    session: SessionDep,
    current_user: RequireAdmin,
) -> InventoryMovement:
    await _require_store(session, store_id)
    await _require_product(session, product_id)
    try:
        _row, movement = await apply_movement(
            session,
            product_id=product_id,
            store_id=store_id,
            delta=payload.delta,
            reason=payload.reason,
            actor_user_id=current_user.id,
            note=payload.note,
        )
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InventoryError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    await session.commit()
    await session.refresh(movement)
    return movement


# --- single-pair audit log --------------------------------------------------


@router.get(
    "/inventory/{store_id}/{product_id}/movements",
    response_model=Page[InventoryMovementResponse],
    summary="Audit log of movements for one (store, product) pair",
)
async def list_movements(
    store_id: UUID,
    product_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
    params: PageParamsDep,
) -> Page[InventoryMovementResponse]:
    base = (
        select(InventoryMovement)
        .where(
            InventoryMovement.store_id == store_id,
            InventoryMovement.product_id == product_id,
        )
        .order_by(InventoryMovement.created_at.desc())
    )
    return await paginate(session, base, params, InventoryMovementResponse)


# --- store-centric: list inventory for one store ----------------------------


@router.get(
    "/stores/{store_id}/inventory",
    response_model=StoreInventoryListResponse,
    summary="Inventory across all products at one store",
)
async def list_store_inventory(
    store_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Case-insensitive name/SKU search."),
    low_stock_only: bool = Query(default=False),
    include_zero: bool = Query(default=True),
) -> StoreInventoryListResponse:
    store = await _require_store(session, store_id)

    base = (
        select(
            Inventory.product_id,
            Inventory.quantity,
            Inventory.reorder_threshold,
            Inventory.updated_at,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
        )
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.store_id == store_id)
    )
    if not include_zero:
        base = base.where(Inventory.quantity > 0)
    if low_stock_only:
        base = base.where(
            Inventory.reorder_threshold.is_not(None),
            Inventory.quantity <= Inventory.reorder_threshold,
        )
    if q:
        needle = f"%{q.lower()}%"
        base = base.where(
            (func.lower(Product.name).like(needle))
            | (func.lower(func.coalesce(Product.sku, "")).like(needle))
        )

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    offset = (page - 1) * limit
    rows = (
        await session.execute(base.order_by(Product.name.asc()).limit(limit).offset(offset))
    ).all()

    return StoreInventoryListResponse(
        store={"id": store.id, "name": store.name, "kind": store.kind},
        items=[
            StoreInventoryRow(
                product_id=r.product_id,
                product_name=r.product_name,
                product_sku=r.product_sku,
                quantity=r.quantity,
                reorder_threshold=r.reorder_threshold,
                updated_at=r.updated_at,
            )
            for r in rows
        ],
        **_page_meta(total, page, limit),
    )


# --- product-centric: list inventory for one product ------------------------


@router.get(
    "/products/{product_id}/inventory",
    response_model=ProductInventoryListResponse,
    summary="Inventory for one product across all stores",
)
async def list_product_inventory(
    product_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_zero: bool = Query(default=True),
) -> ProductInventoryListResponse:
    product = await _require_product(session, product_id)

    base = (
        select(
            Inventory.store_id,
            Inventory.quantity,
            Inventory.reorder_threshold,
            Inventory.updated_at,
            Store.name.label("store_name"),
            Store.kind.label("store_kind"),
        )
        .join(Store, Store.id == Inventory.store_id)
        .where(Inventory.product_id == product_id)
    )
    if not include_zero:
        base = base.where(Inventory.quantity > 0)

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    offset = (page - 1) * limit
    rows = (
        await session.execute(base.order_by(Store.name.asc()).limit(limit).offset(offset))
    ).all()

    return ProductInventoryListResponse(
        product={"id": product.id, "name": product.name, "sku": product.sku},
        items=[
            ProductInventoryRow(
                store_id=r.store_id,
                store_name=r.store_name,
                store_kind=r.store_kind,
                quantity=r.quantity,
                reorder_threshold=r.reorder_threshold,
                updated_at=r.updated_at,
            )
            for r in rows
        ],
        **_page_meta(total, page, limit),
    )
