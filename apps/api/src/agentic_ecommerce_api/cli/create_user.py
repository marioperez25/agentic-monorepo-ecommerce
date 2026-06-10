"""``agentic-ecommerce-create-user`` — create a user from the command line.

Usage:
    uv run agentic-ecommerce-create-user <username> <password> [--role admin|seller|customer]
    uv run agentic-ecommerce-create-user <username> [--role ...]   # prompts for password

Role defaults to ``customer``. Reads ``DATABASE_URL`` from env/.env.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from agentic_ecommerce_api.auth import hash_password
from agentic_ecommerce_api.db import Role, User, get_sessionmaker


async def _create_user(username: str, password: str, role: Role) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"error: user {username!r} already exists", file=sys.stderr)
            sys.exit(1)

        session.add(User(username=username, password_hash=hash_password(password), role=role))
        await session.commit()

    print(f"created user {username!r} (role={role.value})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentic-ecommerce-create-user")
    parser.add_argument("username")
    parser.add_argument("password", nargs="?", default=None)
    parser.add_argument(
        "--role",
        choices=[r.value for r in Role],
        default=Role.CUSTOMER.value,
        help="User role (default: customer).",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("password: ")
    if not password:
        print("error: password may not be empty", file=sys.stderr)
        sys.exit(2)

    asyncio.run(_create_user(args.username, password, Role(args.role)))


if __name__ == "__main__":
    main()
