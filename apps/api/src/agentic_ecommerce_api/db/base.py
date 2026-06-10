"""Async SQLAlchemy engine and session factory.

The engine is constructed lazily on first use so that tests can override
``DATABASE_URL`` before anything else imports this module. ``reset_engine``
exists for tests that need a clean engine bound to a new URL.
"""

from __future__ import annotations

from agentic_ecommerce_shared import get_settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, future=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


def reset_engine() -> None:
    """Drop cached engine and sessionmaker — used by tests."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
