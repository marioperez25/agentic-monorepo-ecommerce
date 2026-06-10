"""Create products table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_products_created_by_users", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index("ix_products_slug", "products", ["slug"], unique=False)
    op.create_index("ix_products_created_by", "products", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_created_by", table_name="products")
    op.drop_index("ix_products_slug", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
