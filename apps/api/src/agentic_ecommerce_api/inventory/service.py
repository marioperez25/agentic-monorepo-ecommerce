"""Inventory mutation primitives.

All writes funnel through ``apply_movement`` so the audit log is always kept
in sync with the snapshot in ``Inventory``. Callers are responsible for
committing the surrounding transaction.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api.db import Inventory, InventoryMovement, MovementReason


class InventoryError(Exception):
    """Base for inventory-domain failures (translated to HTTP by the router)."""


class InsufficientStockError(InventoryError):
    pass


async def _load(session: AsyncSession, product_id: UUID, store_id: UUID) -> Inventory | None:
    return (
        await session.execute(
            select(Inventory).where(
                Inventory.product_id == product_id,
                Inventory.store_id == store_id,
            )
        )
    ).scalar_one_or_none()


async def apply_movement(
    session: AsyncSession,
    *,
    product_id: UUID,
    store_id: UUID,
    delta: int,
    reason: MovementReason,
    actor_user_id: UUID,
    note: str | None = None,
    reorder_threshold: int | None = None,
) -> tuple[Inventory, InventoryMovement]:
    """Apply ``delta`` to (product, store) and record the movement.

    - If no ``Inventory`` row exists, one is created with quantity = delta
      (so ``delta`` must be positive on first touch).
    - Raises ``InsufficientStockError`` if the resulting quantity would be < 0.
    - Does NOT commit — caller wraps in a transaction.
    """
    if delta == 0:
        raise InventoryError("delta must be non-zero")

    row = await _load(session, product_id, store_id)

    if row is None:
        if delta < 0:
            raise InsufficientStockError(
                f"no inventory exists for product {product_id} at store {store_id}"
            )
        row = Inventory(
            product_id=product_id,
            store_id=store_id,
            quantity=delta,
            reorder_threshold=reorder_threshold,
            updated_by=actor_user_id,
        )
        session.add(row)
        quantity_after = delta
    else:
        quantity_after = row.quantity + delta
        if quantity_after < 0:
            raise InsufficientStockError(
                f"would leave quantity at {quantity_after} (current {row.quantity}, delta {delta})"
            )
        row.quantity = quantity_after
        row.updated_by = actor_user_id
        if reorder_threshold is not None:
            row.reorder_threshold = reorder_threshold

    movement = InventoryMovement(
        product_id=product_id,
        store_id=store_id,
        delta=delta,
        reason=reason,
        quantity_after=quantity_after,
        note=note,
        created_by=actor_user_id,
    )
    session.add(movement)
    await session.flush()
    return row, movement


async def set_absolute_quantity(
    session: AsyncSession,
    *,
    product_id: UUID,
    store_id: UUID,
    new_quantity: int,
    actor_user_id: UUID,
    note: str | None = None,
    reorder_threshold: int | None = None,
) -> Inventory:
    """``PUT`` semantics: set absolute quantity, derive the delta.

    When the delta is zero, only the threshold is touched (if supplied) and
    no movement is recorded — movements describe stock changes, not metadata
    edits.
    """
    if new_quantity < 0:
        raise InventoryError("quantity must be >= 0")

    row = await _load(session, product_id, store_id)
    current = row.quantity if row else 0
    delta = new_quantity - current

    if delta != 0:
        row, _movement = await apply_movement(
            session,
            product_id=product_id,
            store_id=store_id,
            delta=delta,
            reason=MovementReason.ADJUSTMENT,
            actor_user_id=actor_user_id,
            note=note,
            reorder_threshold=reorder_threshold,
        )
        return row

    # No-op on quantity. Create the row if it didn't exist, optionally
    # update threshold.
    if row is None:
        row = Inventory(
            product_id=product_id,
            store_id=store_id,
            quantity=0,
            reorder_threshold=reorder_threshold,
            updated_by=actor_user_id,
        )
        session.add(row)
        await session.flush()
    elif reorder_threshold is not None:
        row.reorder_threshold = reorder_threshold
        row.updated_by = actor_user_id
    return row
