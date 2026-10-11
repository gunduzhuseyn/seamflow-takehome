"""A job that logs one line.

arq exits at startup when the worker registers no functions. This job
keeps the list non-empty until the classification job replaces it.
"""

import logging
from typing import Any

log = logging.getLogger("app.jobs")


async def heartbeat(ctx: dict[str, Any]) -> None:
    log.info("heartbeat")
