"""Server-side limits before a call: input size and a per-user rate."""

import time
import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis

# A rough estimate for English text. The real count comes back in usage.
CHARS_PER_TOKEN = 4
WINDOW_SECONDS = 60


def estimate_tokens(*texts: str) -> int:
    return sum(len(text) for text in texts) // CHARS_PER_TOKEN


def check_input_limit(limit: int, *texts: str) -> None:
    estimate = estimate_tokens(*texts)
    if estimate > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Input is about {estimate} tokens. The limit is {limit}.",
        )


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
