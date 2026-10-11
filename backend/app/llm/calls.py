"""Run one structured call and record it.

The caller inserts the `running` row and commits before the call starts.
`run_call` consumes the provider stream, validates the tool input, updates
the row, and commits again.
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import CallStatus, LLMCall
from app.llm.prices import cost_usd
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


class LLMCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_id: uuid.UUID
    request_id: str
    prompt_name: str
    prompt_version: int
    model: str
    status: CallStatus
    input_tokens: int | None
    output_tokens: int | None
    # A float for the browser. The row keeps the exact numeric.
    cost_usd: float | None
    latency_ms: int | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


def _finish[T: BaseModel](
    call: LLMCall,
    output_model: type[T],
    text: str,
    tool_input: dict[str, Any] | None,
    usage: Usage | None,
    error: Error | None,
) -> T | ErrorCode:
    """Set status, result, and error on the row. Return the output or a code."""
    if error is not None:
        call.status, call.error = CallStatus.failed, f"{error.code}: {error.message}"
        return error.code
    if usage is not None and usage.stop_reason in ("refusal", "max_tokens"):
        call.status, call.error = CallStatus.failed, usage.stop_reason
        return "refusal" if usage.stop_reason == "refusal" else "max_tokens"
    if tool_input is None:
        call.status, call.error = CallStatus.invalid_output, f"no tool call\n{text}"
        return "invalid_output"
    try:
        output = output_model.model_validate(tool_input)
    except ValidationError as exc:
        call.status = CallStatus.invalid_output
        call.error = f"{json.dumps(tool_input)}\n{exc}"
        return "invalid_output"
    call.status, call.result = CallStatus.succeeded, output.model_dump(mode="json")
    return output


async def run_call[T: BaseModel](
    session: AsyncSession,
    provider: LLMProvider,
    call: LLMCall,
    request: LLMRequest,
    output_model: type[T],
) -> T | ErrorCode:
    """Consume the stream, then store and return the validated output or a code."""
    started = time.perf_counter()
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
        # A provider bug. The row must not stay `running`.
        log.exception("llm provider raised")
        error = Error(code="provider_error", message=f"{type(exc).__name__}: {exc}")
    _stamp(call, started)
    if usage is not None:
        call.input_tokens, call.output_tokens = (
            usage.input_tokens,
            usage.output_tokens,
        )
        call.cost_usd = cost_usd(call.model, usage.input_tokens, usage.output_tokens)
    outcome = _finish(call, output_model, "".join(text_parts), tool_input, usage, error)
    await session.commit()
    _log(call)
    return outcome


def _stamp(call: LLMCall, started: float) -> None:
    call.latency_ms = int((time.perf_counter() - started) * 1000)
    call.finished_at = datetime.now(UTC)


def _log(call: LLMCall) -> None:
    log.info(
        "llm_call",
        extra={
            "call_id": str(call.id),
            "model": call.model,
            "status": call.status,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
        },
    )
