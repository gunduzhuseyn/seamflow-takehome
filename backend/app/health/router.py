import asyncio
from collections.abc import Awaitable
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.0

Status = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Status
    db: Status
    redis: Status


async def _ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _ping_redis(redis: Redis) -> None:
    await redis.ping()  # pyright: ignore[reportUnknownMemberType]


async def _status(check: Awaitable[None]) -> Status:
    try:
        await asyncio.wait_for(check, CHECK_TIMEOUT_SECONDS)
    except Exception:
        return "error"
    return "ok"


@router.get("/health", responses={503: {"model": HealthResponse}})
async def health(request: Request, response: Response) -> HealthResponse:
    db = await _status(_ping_db(request.app.state.engine))
    redis = await _status(_ping_redis(request.app.state.redis))
    ok = db == "ok" and redis == "ok"
    if not ok:
        response.status_code = 503
    return HealthResponse(status="ok" if ok else "error", db=db, redis=redis)
