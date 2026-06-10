"""Extend user_role to allow 'vendor'

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``native_enum=False`` means the column is VARCHAR + a CHECK constraint
    # named after the enum. To extend the allowed set we drop and recreate
    # the CHECK. ``batch_alter_table`` works on both Postgres and SQLite.
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("user_role", type_="check")
        batch_op.create_check_constraint(
            "user_role",
            "role IN ('admin', 'seller', 'vendor', 'customer')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("user_role", type_="check")
        batch_op.create_check_constraint(
            "user_role",
            "role IN ('admin', 'seller', 'customer')",
        )
