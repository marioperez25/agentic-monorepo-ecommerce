"""Stores CRUD.

Permissions:

    | Action                            | ADMIN | SELLER | VENDOR     | CUSTOMER |
    |-----------------------------------|-------|--------|------------|----------|
    | Create PHYSICAL / ONLINE          |   x   |        |            |          |
    | Create MARKETPLACE (any owner)    |   x   |        |            |          |
    | Create MARKETPLACE (self-owned)   |   x   |        |     x      |   x*     |
    | Read (list + get)                 |   x   |   x    |     x      |   x      |
    | Edit / soft-delete any store      |   x   |        |            |          |
    | Edit / soft-delete OWN marketplace|   x   |        |     x      |          |

    * CUSTOMER who creates a MARKETPLACE store is auto-promoted to VENDOR
      (self-service onboarding).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api._pagination import Page, PageParamsDep, paginate
from agentic_ecommerce_api.auth import CurrentUser
from agentic_ecommerce_api.db import Role, Store, StoreKind, get_session
from agentic_ecommerce_api.products import slugify
from agentic_ecommerce_api.stores import (
    StoreCreate,
    StoreResponse,
    StoreUpdate,
)

router = APIRouter(prefix="/stores", tags=["stores"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to modify this store"
)
_CONFLICT_RESPONSE = {
    "description": "A store with the same slug already exists.",
    "content": {"application/json": {"example": {"detail": "slug already in use"}}},
}


def _validate_kind_specific_fields(payload: StoreCreate) -> None:
    """Mirror the DB CHECK constraints with a clearer 422 message."""
    if payload.kind == StoreKind.PHYSICAL:
        missing = [
            name
            for name, value in (
                ("address_line1", payload.address_line1),
                ("city", payload.city),
                ("country", payload.country),
            )
            if value is None
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"physical stores require: {', '.join(missing)}",
            )
    elif payload.kind == StoreKind.ONLINE:
        if not payload.domain:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="online stores require: domain",
            )
        if payload.owner_user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="online stores cannot have an owner_user_id",
            )


async def _load_store(session: AsyncSession, store_id: UUID) -> Store:
    store = (await session.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if store is None or not store.is_active:
        raise _NOT_FOUND
    return store


def _raise_conflict() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="slug already in use",
    )


@router.post(
    "",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a store",
    description=(
        "Creating a MARKETPLACE store as a CUSTOMER auto-promotes you to VENDOR. "
        "Only ADMIN can create PHYSICAL or ONLINE stores, or assign an arbitrary "
        "owner to a MARKETPLACE store."
    ),
    responses={
        403: {"description": "Caller lacks the role for this kind."},
        409: _CONFLICT_RESPONSE,
    },
)
async def create_store(
    payload: StoreCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Store:
    # --- role gating ---
    if payload.kind in (StoreKind.PHYSICAL, StoreKind.ONLINE):
        if current_user.role != Role.ADMIN:
            raise _FORBIDDEN
    elif payload.kind == StoreKind.MARKETPLACE:
        if current_user.role == Role.SELLER:
            raise _FORBIDDEN
        # ADMIN / VENDOR / CUSTOMER may proceed.

    _validate_kind_specific_fields(payload)

    # --- owner resolution for MARKETPLACE ---
    owner_user_id: UUID | None = None
    if payload.kind == StoreKind.MARKETPLACE:
        if current_user.role == Role.ADMIN and payload.owner_user_id is not None:
            owner_user_id = payload.owner_user_id
        else:
            owner_user_id = current_user.id
            if current_user.role == Role.CUSTOMER:
                # Self-service onboarding: auto-promote to VENDOR.
                current_user.role = Role.VENDOR

    slug = payload.slug or slugify(payload.name)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not derive a slug from `name`; provide `slug` explicitly.",
        )

    store = Store(
        kind=payload.kind,
        name=payload.name,
        slug=slug,
        description=payload.description,
        currency=payload.currency.upper(),
        timezone=payload.timezone,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        region=payload.region,
        country=payload.country.upper() if payload.country else None,
        postal_code=payload.postal_code,
        latitude=payload.latitude,
        longitude=payload.longitude,
        phone=payload.phone,
        contact_email=payload.contact_email,
        domain=payload.domain,
        owner_user_id=owner_user_id,
        created_by=current_user.id,
    )
    session.add(store)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_conflict()
    await session.refresh(store)
    return store


@router.get("", response_model=Page[StoreResponse], summary="List stores (paginated)")
async def list_stores(
    session: SessionDep,
    _current_user: CurrentUser,
    params: PageParamsDep,
    q: str | None = Query(default=None, description="Case-insensitive search on name or slug."),
    kind: StoreKind | None = None,
    owner_user_id: UUID | None = None,
    include_inactive: bool = Query(default=False),
) -> Page[StoreResponse]:
    base = select(Store)
    if not include_inactive:
        base = base.where(Store.is_active.is_(True))
    if kind is not None:
        base = base.where(Store.kind == kind)
    if owner_user_id is not None:
        base = base.where(Store.owner_user_id == owner_user_id)
    if q:
        needle = f"%{q.lower()}%"
        base = base.where(
            or_(func.lower(Store.name).like(needle), func.lower(Store.slug).like(needle))
        )
    base = base.order_by(Store.created_at.desc())
    return await paginate(session, base, params, StoreResponse)


@router.get("/{store_id}", response_model=StoreResponse, summary="Get one store")
async def get_store(
    store_id: UUID,
    session: SessionDep,
    _current_user: CurrentUser,
) -> Store:
    return await _load_store(session, store_id)


def _can_modify(store: Store, user_id: UUID, role: Role) -> bool:
    if role == Role.ADMIN:
        return True
    if (
        role == Role.VENDOR
        and store.kind == StoreKind.MARKETPLACE
        and store.owner_user_id == user_id
    ):
        return True
    return False


@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Update a store",
    responses={
        403: {"description": "Caller is not allowed to modify this store."},
        409: _CONFLICT_RESPONSE,
    },
)
async def update_store(
    store_id: UUID,
    payload: StoreUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Store:
    store = await _load_store(session, store_id)
    if not _can_modify(store, current_user.id, current_user.role):
        raise _FORBIDDEN

    changes = payload.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"] is not None:
        changes["currency"] = changes["currency"].upper()
    if "country" in changes and changes["country"] is not None:
        changes["country"] = changes["country"].upper()
    for field, value in changes.items():
        setattr(store, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_conflict()
    await session.refresh(store)
    return store


@router.delete(
    "/{store_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a store",
    responses={403: {"description": "Caller is not allowed to modify this store."}},
)
async def delete_store(
    store_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Response:
    store = await _load_store(session, store_id)
    if not _can_modify(store, current_user.id, current_user.role):
        raise _FORBIDDEN
    store.is_active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
