"""Create stores table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum(
                "physical",
                "online",
                "marketplace",
                name="store_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        # physical
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        # online
        sa.Column("domain", sa.String(length=255), nullable=True),
        # marketplace
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        # audit
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
            ["owner_user_id"],
            ["users.id"],
            name="fk_stores_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_stores_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("slug", name="uq_stores_slug"),
        sa.CheckConstraint(
            "kind != 'physical' OR ("
            "address_line1 IS NOT NULL AND city IS NOT NULL AND country IS NOT NULL"
            ")",
            name="ck_stores_physical_address",
        ),
        sa.CheckConstraint(
            "kind != 'online' OR (domain IS NOT NULL AND owner_user_id IS NULL)",
            name="ck_stores_online_domain",
        ),
        sa.CheckConstraint(
            "kind != 'marketplace' OR owner_user_id IS NOT NULL",
            name="ck_stores_marketplace_owner",
        ),
    )
    op.create_index("ix_stores_kind", "stores", ["kind"], unique=False)
    op.create_index("ix_stores_name", "stores", ["name"], unique=False)
    op.create_index("ix_stores_slug", "stores", ["slug"], unique=False)
    op.create_index("ix_stores_owner_user_id", "stores", ["owner_user_id"], unique=False)
    op.create_index("ix_stores_created_by", "stores", ["created_by"], unique=False)
    op.create_index("ix_stores_country_city", "stores", ["country", "city"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stores_country_city", table_name="stores")
    op.drop_index("ix_stores_created_by", table_name="stores")
    op.drop_index("ix_stores_owner_user_id", table_name="stores")
    op.drop_index("ix_stores_slug", table_name="stores")
    op.drop_index("ix_stores_name", table_name="stores")
    op.drop_index("ix_stores_kind", table_name="stores")
    op.drop_table("stores")
