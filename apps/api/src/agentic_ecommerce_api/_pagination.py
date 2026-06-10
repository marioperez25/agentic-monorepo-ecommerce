"""Shared pagination primitives.

Every list endpoint in this API should use ``page_params`` for query input
and ``paginate`` for query execution so the response shape stays consistent
(``{ items, total, page, limit, total_pages }``).

If you're tempted to hand-roll pagination, *don't* — instead either extend
this helper or, for join queries that return labeled rows (not ORM objects),
copy the count/offset pattern verbatim.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PageParams(BaseModel):
    """Resolved page + limit, with a derived offset."""

    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    page: Annotated[int, Query(ge=1, description="1-indexed page number.")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page (max 100).")] = 20,
) -> PageParams:
    """FastAPI dependency. Use as: ``params: Annotated[PageParams, Depends(page_params)]``."""
    return PageParams(page=page, limit=limit)


PageParamsDep = Annotated[PageParams, Depends(page_params)]


class Page[T: BaseModel](BaseModel):
    """Standard list-response envelope."""

    items: list[T]
    total: int
    page: int
    limit: int
    total_pages: int


async def paginate[T: BaseModel](
    session: AsyncSession,
    base: Select,
    params: PageParams,
    response_model: type[T],
) -> Page[T]:
    """Execute ``base`` (a ``select(Model)``) with pagination + count.

    Two queries run: a ``COUNT`` over the (unordered) base, then the page
    itself. Caller is responsible for ``order_by`` on ``base`` so paging is
    deterministic.

    Only works for queries that yield ORM scalars (``.scalars().all()``).
    For labeled-column join queries, copy this function's two-query pattern
    inline — there's no clean generic shape for those.
    """
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.limit(params.limit).offset(params.offset))).scalars().all()
    return Page[T](
        items=[response_model.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=(total + params.limit - 1) // params.limit if total else 0,
    )
