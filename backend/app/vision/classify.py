"""Classify one image: the prompt, the tool, and one `llm_calls` row per attempt.

The worker calls `classify_image` with the resized JPEG. Each row is
committed as its attempt ends, so a failed attempt is on record when the
job retries, and a cancelled job keeps the rows of the attempts that ran.
"""

import base64
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.request_id import current_request_id
from app.llm.complete import Attempt, complete_with_tool
from app.llm.limits import check_input_limit
from app.llm.models import LLMCall
from app.llm.prices import cost_usd
from app.llm.prompts import load_prompt
from app.llm.provider import ImageInput, LLMProvider, LLMRequest
from app.vision.schema import VisionResult, tool_schema

log = logging.getLogger("app.vision")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_NAME = "classify"
TOOL_NAME = "record_verdict"
TOOL_DESCRIPTION = "Record the verdict for the image."
# The question goes in the user turn as data, in tags the system prompt
# names. The system prompt itself is fixed.
USER_TEXT = (
    "<subject>{question_label}</subject>\n"
    "Decide whether the attached image shows the subject. "
    "Answer with the record_verdict tool."
)


@dataclass(frozen=True)
class ClassifyOutcome:
    result: VisionResult
    # The row of the attempt that gave the result.
    llm_call_id: uuid.UUID
    # Over every attempt, so a retried call is paid for.
    cost_usd: Decimal
    latency_ms: int


async def classify_image(
    session: AsyncSession,
    provider: LLMProvider,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    jpeg_bytes: bytes,
    *,
    question_label: str,
    settings: Settings,
) -> ClassifyOutcome:
    check_input_limit(settings.LLM_MAX_IMAGE_BYTES, jpeg_bytes)
    prompt = load_prompt(PROMPT_NAME, PROMPTS_DIR)
    request = LLMRequest(
        model=settings.LLM_MODEL,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        system=prompt.text,
        user=USER_TEXT.format(question_label=question_label),
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        tool_schema=tool_schema(),
        images=[
            ImageInput(
                media_type="image/jpeg",
                data_base64=base64.b64encode(jpeg_bytes).decode(),
            )
        ],
    )
    calls: list[LLMCall] = []

    async def record(attempt: Attempt) -> None:
        calls.append(
            await _record(
                session,
                attempt,
                org_id=org_id,
                user_id=user_id,
                subject_id=subject_id,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                model=request.model,
            )
        )

    outcome = await complete_with_tool(provider, request, VisionResult, record)
    return ClassifyOutcome(
        result=outcome.parsed,
        llm_call_id=calls[-1].id,
        cost_usd=sum(
            (call.cost_usd for call in calls if call.cost_usd is not None),
            Decimal(0),
        ),
        latency_ms=sum(call.latency_ms or 0 for call in calls),
    )


async def _record(session: AsyncSession, attempt: Attempt, **ids: object) -> LLMCall:
    """Insert and commit the row of one attempt."""
    call = LLMCall(
        id=uuid.uuid4(),
        request_id=current_request_id(),
        status=attempt.status,
        latency_ms=attempt.latency_ms,
        result=attempt.result,
        error=attempt.error,
        created_at=attempt.started_at,
        finished_at=attempt.finished_at,
        **ids,
    )
    if attempt.usage is not None:
        call.input_tokens = attempt.usage.input_tokens
        call.output_tokens = attempt.usage.output_tokens
        call.cost_usd = cost_usd(
            call.model, attempt.usage.input_tokens, attempt.usage.output_tokens
        )
    session.add(call)
    await session.commit()
    log.info(
        "llm_call",
        extra={
            "call_id": str(call.id),
            "subject_id": str(call.subject_id),
            "model": call.model,
            "status": call.status,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
        },
    )
    return call
