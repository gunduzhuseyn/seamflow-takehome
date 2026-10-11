"""`python -m app.storage`: create the bucket and its CORS rule. Development only."""

import asyncio
import logging

from app.core.config import Settings
from app.core.logging import configure_logging
from app.storage.client import S3Storage

log = logging.getLogger("app.storage")


def main() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings)
    asyncio.run(S3Storage.from_settings(settings).ensure_bucket())
    log.info("storage ready", extra={"bucket": settings.STORAGE_BUCKET})


if __name__ == "__main__":
    main()
