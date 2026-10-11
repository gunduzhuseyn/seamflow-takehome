"""One structured call: consume the stream, validate the tool input, retry once.

`complete_with_tool` returns the validated output and the usage of the
attempt that produced it. `on_attempt` runs as each attempt ends, so the
caller stores its `llm_calls` row before the next attempt starts and a
cancelled job keeps the rows of the attempts that finished. Every attempt
is also on the result or on the error.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.models import CallStatus
from app.llm.provider import (
    Error,
    ErrorCode,
    LLMProvider,
    LLMRequest,
    TextDelta,
    ToolInput,
    Usage,
)

log = logging.getLogger("app.llm")

# One retry on invalid output. Provider errors go to the caller at once.
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class Attempt:
    """What one provider call produced, in the shape of an `llm_calls` row."""

    status: CallStatus
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    usage: Usage | None
    result: dict[str, Any] | None
    error: str | None
    code: ErrorCode | None


@dataclass(frozen=True)
class ToolResult[T]:
    parsed: T
    usage: Usage
    attempts: tuple[Attempt, ...]


class LLMCallError(Exception):
    """No usable output. `code` says why. `attempts` has every try."""

    def __init__(
        self, code: ErrorCode, message: str, attempts: tuple[Attempt, ...]
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code: ErrorCode = code
        self.message = message
        self.attempts = attempts


class LLMOutputError(LLMCallError):
    """The model answered every attempt, and no tool input validated."""


OnAttempt = Callable[[Attempt], Awaitable[None]]


async def _ignore(attempt: Attempt) -> None:
    pass


async def complete_with_tool[T: BaseModel](
    provider: LLMProvider,
    request: LLMRequest,
    output_model: type[T],
    on_attempt: OnAttempt = _ignore,
) -> ToolResult[T]:
    attempts: list[Attempt] = []
    for _ in range(MAX_ATTEMPTS):
        attempt, parsed = await _attempt(provider, request, output_model)
        attempts.append(attempt)
        await on_attempt(attempt)
        if parsed is not None and attempt.usage is not None:
            return ToolResult(parsed, attempt.usage, tuple(attempts))
        if attempt.code != "invalid_output":
            raise LLMCallError(
                attempt.code or "provider_error", attempt.error or "", tuple(attempts)
            )
        log.info("llm invalid output, retrying", extra={"model": request.model})
    last = attempts[-1]
    raise LLMOutputError("invalid_output", last.error or "", tuple(attempts))


async def _attempt[T: BaseModel](
    provider: LLMProvider, request: LLMRequest, output_model: type[T]
) -> tuple[Attempt, T | None]:
    started_at = datetime.now(UTC)
    clock = time.perf_counter()
    text_parts: list[str] = []
    tool_input: dict[str, Any] | None = None
    usage: Usage | None = None
    error: Error | None = None
    try:
        async for event in provider.stream(request):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                case ToolInput(input=parsed):
                    tool_input = parsed
                case Usage():
                    usage = event
                case Error():
                    error = event
    except Exception as exc:
        # A provider bug. The attempt still gets a row.
        log.exception("llm provider raised")
        error = Error(code="provider_error", message=f"{type(exc).__name__}: {exc}")
    latency_ms = int((time.perf_counter() - clock) * 1000)
    status, code, message, parsed = _judge(
        output_model, "".join(text_parts), tool_input, usage, error
    )
    attempt = Attempt(
        status=status,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        latency_ms=latency_ms,
        usage=usage,
        result=parsed.model_dump(mode="json") if parsed is not None else None,
        error=message,
        code=code,
    )
    return attempt, parsed


def _judge[T: BaseModel](
    output_model: type[T],
    text: str,
    tool_input: dict[str, Any] | None,
    usage: Usage | None,
    error: Error | None,
) -> tuple[CallStatus, ErrorCode | None, str | None, T | None]:
    """The row status, the error code, the error text, and the output."""
    if error is not None:
        return CallStatus.failed, error.code, f"{error.code}: {error.message}", None
    if usage is None:
        return CallStatus.failed, "provider_error", "stream ended early", None
    if usage.stop_reason in ("refusal", "max_tokens"):
        code: ErrorCode = "refusal" if usage.stop_reason == "refusal" else "max_tokens"
        return CallStatus.failed, code, usage.stop_reason, None
    if tool_input is None:
        return (
            CallStatus.invalid_output,
            "invalid_output",
            f"no tool call\n{text}",
            None,
        )
    try:
        output = output_model.model_validate(tool_input)
    except ValidationError as exc:
        message = f"{json.dumps(tool_input)}\n{exc}"
        return CallStatus.invalid_output, "invalid_output", message, None
    return CallStatus.succeeded, None, None, output
