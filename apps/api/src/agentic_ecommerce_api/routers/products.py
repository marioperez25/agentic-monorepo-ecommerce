from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api._pagination import Page, PageParamsDep, paginate
from agentic_ecommerce_api.auth import CurrentUser, RequireAdmin
from agentic_ecommerce_api.db import MovementReason, Product, Store, get_session
from agentic_ecommerce_api.inventory.service import InventoryError, apply_movement
from agentic_ecommerce_api.products import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    slugify,
)

router = APIRouter(prefix="/products", tags=["products"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You can only modify products you created.",
)
_CONFLICT_RESPONSE = {
    "description": "A product with the same slug or SKU already exists.",
    "content": {"application/json": {"example": {"detail": "slug or sku already in use"}}},
}


async def _load_product(session: AsyncSession, product_id: UUID) -> Product:
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None or not product.is_active:
        raise _NOT_FOUND
    return product


def _raise_conflict() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="slug or sku already in use",
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product (ADMIN only)",
    responses={
        403: {"description": "Caller is not an ADMIN."},
        409: _CONFLICT_RESPONSE,
    },
)
async def create_product(
    payload: ProductCreate,
    session: SessionDep,
    current_user: RequireAdmin,
) -> Product:
    slug = payload.slug or slugify(payload.name)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not derive a slug from `name`; provide `slug` explicitly.",
        )

    # Validate all referenced stores up-front so the whole call fails cleanly
    # rather than mid-transaction.
    if payload.initial_inventory:
        store_ids = [item.store_id for item in payload.initial_inventory]
        if len(set(store_ids)) != len(store_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="initial_inventory contains duplicate store_id entries.",
            )
        found = (
            (
                await session.execute(
                    select(Store.id).where(Store.id.in_(store_ids), Store.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        missing = set(store_ids) - set(found)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"unknown or inactive store_id(s): {sorted(str(s) for s in missing)}",
            )

    product = Product(
        name=payload.name,
        slug=slug,
        description=payload.description,
        price_cents=payload.price_cents,
        currency=payload.currency.upper(),
        sku=payload.sku,
        created_by=current_user.id,
    )
    session.add(product)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        _raise_conflict()

    for item in payload.initial_inventory:
        if item.quantity == 0:
            # Skip zero-qty entries: a movement with delta=0 violates a CHECK.
            # The client can call PUT later to set the threshold without stock.
            continue
        try:
            await apply_movement(
                session,
                product_id=product.id,
                store_id=item.store_id,
                delta=item.quantity,
                reason=MovementReason.INITIAL,
                actor_user_id=current_user.id,
                reorder_threshold=item.reorder_threshold,
            )
        except InventoryError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    await session.commit()
    await session.refresh(product)
    return product


@router.get(
    "",
    response_model=Page[ProductResponse],
    summary="List products (paginated)",
)
async def list_products(
    session: SessionDep,
    _current_user: CurrentUser,
    params: PageParamsDep,
    q: str | None = Query(default=None, description="Case-insensitive search on name or slug."),
    include_inactive: bool = Query(default=False),
) -> Page[ProductResponse]:
    base = select(Product)
    if not include_inactive:
        base = base.where(Product.is_active.is_(True))
    if q:
        needle = f"%{q.lower()}%"
        base = base.where(
            or_(func.lower(Product.name).like(needle), func.lower(Product.slug).like(needle))
        )
    base = base.order_by(Product.created_at.desc())
    return await paginate(session, base, params, ProductResponse)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get one product",
)
async def get_product(
    product_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
) -> Product:
    return await _load_product(session, product_id)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product (ADMIN, creator-only)",
    responses={
        403: {"description": "Caller is not an ADMIN, or not the original creator."},
        409: _CONFLICT_RESPONSE,
    },
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    session: SessionDep,
    current_user: RequireAdmin,
) -> Product:
    product = await _load_product(session, product_id)
    if product.created_by != current_user.id:
        raise _FORBIDDEN

    changes = payload.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"] is not None:
        changes["currency"] = changes["currency"].upper()
    for field, value in changes.items():
        setattr(product, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_conflict()
    await session.refresh(product)
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a product (ADMIN, creator-only)",
    responses={
        403: {"description": "Caller is not an ADMIN, or not the original creator."},
    },
)
async def delete_product(
    product_id: UUID,
    session: SessionDep,
    current_user: RequireAdmin,
) -> Response:
    product = await _load_product(session, product_id)
    if product.created_by != current_user.id:
        raise _FORBIDDEN
    product.is_active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
