"""The arq worker. Start it with `uv run arq app.worker.WorkerSettings`.

It reads the same settings as the API. Each job gets the context that
`on_startup` builds: the sessionmaker and the settings.
"""

import logging
from typing import Any

from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine

from app.core.config import Settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging

log = logging.getLogger("app.worker")

settings = Settings()  # pyright: ignore[reportCallIssue]


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(settings)
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["sessionmaker"] = create_sessionmaker(engine)
    ctx["settings"] = settings
    log.info("worker started", extra={"queue": settings.WORKER_QUEUE_NAME})


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    log.info("worker stopped")


class WorkerSettings:
    # arq refuses to start with no functions. The first job kind registers here.
    functions: list[WorkerCoroutine] = []
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    queue_name = settings.WORKER_QUEUE_NAME
    # The runner stops before this. arq never sees a try past max_attempts.
    max_tries = settings.WORKER_MAX_ATTEMPTS
    job_timeout = settings.WORKER_JOB_TIMEOUT_SECONDS
