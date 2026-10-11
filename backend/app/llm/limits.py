"""Server-side limits before a call: the model input size and a per-user rate."""

import time
import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis

WINDOW_SECONDS = 60


class InputTooLargeError(Exception):
    """The model input is over LLM_MAX_IMAGE_BYTES. The worker raises it."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"Model input is {size} bytes. The limit is {limit}.")
        self.size = size
        self.limit = limit


def check_input_limit(limit: int, data: bytes) -> None:
    if len(data) > limit:
        raise InputTooLargeError(len(data), limit)


async def enforce_rate_limit(redis: Redis, user_id: uuid.UUID, limit: int) -> None:
    """Count calls per user in the current clock minute. The N+1th is 429."""
    now = int(time.time())
    window = now // WINDOW_SECONDS
    key = f"llm:rate:{user_id}:{window}"
    count: int = await redis.incr(key)  # pyright: ignore[reportUnknownMemberType]
    if count == 1:
        await redis.expire(key, WINDOW_SECONDS * 2)  # pyright: ignore[reportUnknownMemberType]
    if count > limit:
        retry_after = WINDOW_SECONDS - now % WINDOW_SECONDS
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"At most {limit} calls per minute. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
