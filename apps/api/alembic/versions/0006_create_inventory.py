"""Create inventory + inventory_movements

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REASONS = ("initial", "restock", "adjustment", "sale", "return", "shrinkage", "transfer")


def upgrade() -> None:
    op.create_table(
        "inventory",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_threshold", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("product_id", "store_id"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_inventory_product_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name="fk_inventory_store_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_inventory_updated_by", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_quantity_nonneg"),
        sa.CheckConstraint(
            "reorder_threshold IS NULL OR reorder_threshold >= 0",
            name="ck_inventory_threshold_nonneg",
        ),
    )
    # store_id-first index for "list all stock at this store" scans.
    op.create_index("ix_inventory_store_id", "inventory", ["store_id"], unique=False)

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                *_REASONS,
                name="movement_reason",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_inv_mov_product_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name="fk_inv_mov_store_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_inv_mov_created_by", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("quantity_after >= 0", name="ck_inv_mov_qty_after_nonneg"),
        sa.CheckConstraint("delta != 0", name="ck_inv_mov_delta_nonzero"),
    )
    op.create_index("ix_inv_mov_product_id", "inventory_movements", ["product_id"])
    op.create_index("ix_inv_mov_store_id", "inventory_movements", ["store_id"])
    op.create_index("ix_inv_mov_created_by", "inventory_movements", ["created_by"])
    op.create_index("ix_inv_mov_created_at", "inventory_movements", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_inv_mov_created_at", table_name="inventory_movements")
    op.drop_index("ix_inv_mov_created_by", table_name="inventory_movements")
    op.drop_index("ix_inv_mov_store_id", table_name="inventory_movements")
    op.drop_index("ix_inv_mov_product_id", table_name="inventory_movements")
    op.drop_table("inventory_movements")

    op.drop_index("ix_inventory_store_id", table_name="inventory")
    op.drop_table("inventory")
