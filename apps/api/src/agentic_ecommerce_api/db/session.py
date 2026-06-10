from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agentic_ecommerce_api.db.base import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session and closes it after the request."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
