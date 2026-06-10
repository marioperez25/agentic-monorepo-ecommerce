from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentic_ecommerce_api.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    """Authenticated user role. `GUEST` is modeled as the absence of a token,
    not stored here."""

    ADMIN = "admin"
    SELLER = "seller"  # internal POS staff added by an admin
    VENDOR = "vendor"  # marketplace seller; manages own marketplace stores only
    CUSTOMER = "customer"


class StoreKind(StrEnum):
    PHYSICAL = "physical"  # brick-and-mortar POS location
    ONLINE = "online"  # platform-owned online storefront (multi-brand supported)
    MARKETPLACE = "marketplace"  # vendor storefront owned by a user


class MovementReason(StrEnum):
    INITIAL = "initial"  # first stock set at product creation
    RESTOCK = "restock"  # incoming shipment
    ADJUSTMENT = "adjustment"  # manual correction (count discrepancy)
    SALE = "sale"  # negative; recorded when an order ships
    RETURN = "return"  # positive; customer return
    SHRINKAGE = "shrinkage"  # negative; theft/damage/loss
    TRANSFER = "transfer"  # store-to-store transfer (sign indicates direction)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=False, length=16),
        nullable=False,
        default=Role.CUSTOMER,
        server_default=Role.CUSTOMER.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class Store(Base):
    __tablename__ = "stores"

    # --- shared ---
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[StoreKind] = mapped_column(
        Enum(StoreKind, name="store_kind", native_enum=False, length=16),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- physical-only ---
    address_line1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- online-only ---
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- marketplace-only ---
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    # --- audit ---
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "kind != 'physical' OR ("
            "address_line1 IS NOT NULL AND city IS NOT NULL AND country IS NOT NULL"
            ")",
            name="ck_stores_physical_address",
        ),
        CheckConstraint(
            "kind != 'online' OR (domain IS NOT NULL AND owner_user_id IS NULL)",
            name="ck_stores_online_domain",
        ),
        CheckConstraint(
            "kind != 'marketplace' OR owner_user_id IS NOT NULL",
            name="ck_stores_marketplace_owner",
        ),
    )


class Inventory(Base):
    """Current stock for a (product, store) pair. Source of truth for reads.

    Every write to ``quantity`` must be accompanied by an ``InventoryMovement``
    row written in the same transaction. The router enforces this — no other
    code path mutates this table directly.
    """

    __tablename__ = "inventory"

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_nonneg"),
        CheckConstraint(
            "reorder_threshold IS NULL OR reorder_threshold >= 0",
            name="ck_inventory_threshold_nonneg",
        ),
    )


class InventoryMovement(Base):
    """Append-only audit log for every change to ``Inventory.quantity``."""

    __tablename__ = "inventory_movements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[MovementReason] = mapped_column(
        Enum(MovementReason, name="movement_reason", native_enum=False, length=20),
        nullable=False,
    )
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_utcnow,
        index=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("quantity_after >= 0", name="ck_inv_mov_qty_after_nonneg"),
        CheckConstraint("delta != 0", name="ck_inv_mov_delta_nonzero"),
    )
