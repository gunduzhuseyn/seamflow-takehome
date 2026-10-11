"""One request id per request: from X-Request-Id, else a new uuid.

The id is on the response and in a contextvar, so the LLM call record and
the log lines carry it.
"""

import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = b"x-request-id"
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    return request_id_var.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        request_id = (
            headers.get(HEADER, b"").decode("latin-1")[:128] or uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (HEADER, request_id.encode("latin-1")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)
