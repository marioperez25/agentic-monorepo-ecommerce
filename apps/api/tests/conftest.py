"""Shared test fixtures for the API.

Sets up env vars *before* importing the app so ``get_settings()`` caches the
test config. Tests use an in-memory SQLite via ``aiosqlite`` so they need no
external services. The ``StaticPool`` keeps a single connection alive so the
``:memory:`` database persists across the session.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-for-tests-only-needs-to-be-at-least-32-bytes",
)
# Disable the slowapi limiter for the suite — tests run many login calls
# from the same loopback IP and would otherwise trip per-IP limits.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from agentic_ecommerce_api import app  # noqa: E402
from agentic_ecommerce_api.auth import hash_password  # noqa: E402
from agentic_ecommerce_api.db import Role, User  # noqa: E402
from agentic_ecommerce_api.db.base import Base  # noqa: E402
from agentic_ecommerce_api.db.session import get_session  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> User:
    """ADMIN user. Most existing tests assume Alice can do anything."""
    user = User(
        username="alice",
        password_hash=hash_password("correct-password"),
        role=Role.ADMIN,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def carol(db_session: AsyncSession) -> User:
    """CUSTOMER user — used to test role-gating rejects non-admins."""
    user = User(
        username="carol",
        password_hash=hash_password("carol-password"),
        role=Role.CUSTOMER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sam(db_session: AsyncSession) -> User:
    """SELLER user — used to test SELLER access (orders later, no products)."""
    user = User(
        username="sam",
        password_hash=hash_password("sam-password"),
        role=Role.SELLER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def vince(db_session: AsyncSession) -> User:
    """VENDOR user — owns marketplace stores."""
    user = User(
        username="vince",
        password_hash=hash_password("vince-password"),
        role=Role.VENDOR,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
