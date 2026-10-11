"""One log line per request, written when the response is complete.

The auth dependencies put `user_id` and `org_id` on request.state. The line
carries them when they are present. An unhandled exception gives one ERROR
line, and the client gets a 500 that still carries the request id.
"""

import logging
import time
from typing import Any

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_id import current_request_id

log = logging.getLogger("app.access")

# Health checks run every few seconds. Their lines are DEBUG.
QUIET_PATHS = {"/health"}


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        # Request.state reads and writes this dict.
        state: dict[str, Any] = scope.setdefault("state", {})
        # A dict, so the closure below can set it.
        response: dict[str, int] = {}

        async def send_with_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
            await send(message)

        def fields() -> dict[str, Any]:
            return {
                "request_id": current_request_id(),
                "method": scope["method"],
                "path": scope["path"],
                "status": response.get("status"),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "user_id": state.get("user_id"),
                "org_id": state.get("org_id"),
            }

        try:
            await self.app(scope, receive, send_with_status)
        except Exception:
            if "status" in response:
                # The response has started. Only the server can end it.
                log.exception("request failed", extra=fields())
                raise
            response["status"] = 500
            log.exception("request failed", extra=fields())
            error = PlainTextResponse("Internal Server Error", status_code=500)
            await error(scope, receive, send)
            return
        level = logging.DEBUG if scope["path"] in QUIET_PATHS else logging.INFO
        log.log(level, "request", extra=fields())
