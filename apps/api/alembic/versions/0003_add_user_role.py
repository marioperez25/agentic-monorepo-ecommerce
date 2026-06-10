"""Add role column to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ROLES = ("admin", "seller", "customer")


def upgrade() -> None:
    role_type = sa.Enum(
        *_ROLES,
        name="user_role",
        native_enum=False,
        length=16,
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            role_type,
            nullable=False,
            server_default="customer",
        ),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")
