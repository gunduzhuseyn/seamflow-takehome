"""`complete_with_tool` on the fake provider: validation, one retry, errors."""

import pytest

from app.llm.complete import LLMCallError, LLMOutputError, complete_with_tool
from app.llm.fake_provider import FakeProvider
from app.llm.models import CallStatus
from app.llm.provider import ImageInput, LLMRequest
from app.vision.schema import VisionResult, tool_schema

REQUEST = LLMRequest(
    model="claude-sonnet-5-5",
    max_output_tokens=256,
    system="Classify the image.",
    user="Use the record_verdict tool.",
    tool_name="record_verdict",
    tool_description="Record the verdict.",
    tool_schema=tool_schema(),
    images=[ImageInput(media_type="image/jpeg", data_base64="/9j/4AAQ")],
)


async def test_valid_output_is_parsed_in_one_attempt() -> None:
    provider = FakeProvider(fixture="hotdog")

    result = await complete_with_tool(provider, REQUEST, VisionResult)

    assert result.parsed.verdict == "match"
    assert result.parsed.confidence == 0.97
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1600, 60)
    assert [a.status for a in result.attempts] == [CallStatus.succeeded]
    assert result.attempts[0].result == result.parsed.model_dump(mode="json")
    # The fake records the images with the request.
    assert provider.requests[0].images == REQUEST.images


async def test_invalid_output_is_retried_once_then_raises() -> None:
    provider = FakeProvider(fixture="hotdog_invalid")

    with pytest.raises(LLMOutputError) as exc_info:
        await complete_with_tool(provider, REQUEST, VisionResult)

    assert exc_info.value.code == "invalid_output"
    assert len(provider.requests) == 2
    attempts = exc_info.value.attempts
    assert [a.status for a in attempts] == [CallStatus.invalid_output] * 2
    assert attempts[0].error is not None
    assert "sausage" in attempts[0].error
    assert attempts[0].usage is not None


async def test_valid_output_on_the_second_attempt_succeeds() -> None:
    provider = FakeProvider(fixture="hotdog")
    provider.queue = ["hotdog_invalid"]

    result = await complete_with_tool(provider, REQUEST, VisionResult)

    assert result.parsed.verdict == "match"
    assert [a.status for a in result.attempts] == [
        CallStatus.invalid_output,
        CallStatus.succeeded,
    ]


@pytest.mark.parametrize(
    ("fixture", "code"),
    [("refusal", "refusal"), ("max_tokens", "max_tokens")],
)
async def test_a_stop_reason_is_not_retried(fixture: str, code: str) -> None:
    provider = FakeProvider(fixture=fixture)

    with pytest.raises(LLMCallError) as exc_info:
        await complete_with_tool(provider, REQUEST, VisionResult)

    assert exc_info.value.code == code
    assert not isinstance(exc_info.value, LLMOutputError)
    assert len(provider.requests) == 1
    assert exc_info.value.attempts[0].status is CallStatus.failed
