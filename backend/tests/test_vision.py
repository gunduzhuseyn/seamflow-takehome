"""`classify_image` on the fake provider: the request, the rows, the retry."""

import asyncio
import base64
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.complete import LLMOutputError
from app.llm.fake_provider import FakeProvider
from app.llm.limits import InputTooLargeError
from app.vision.classify import TOOL_NAME, classify_image
from tests.jobs_support import Owner, owner

__all__ = ["owner"]

JPEG = b"\xff\xd8\xff\xe0 not really a jpeg"


async def stored_calls(
    session: AsyncSession, subject_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        text("SELECT * FROM llm_calls WHERE subject_id = :id ORDER BY created_at"),
        {"id": subject_id},
    )
    return [dict(row) for row in result.mappings().all()]


async def test_classify_records_one_succeeded_row(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    org, user = owner
    subject_id = uuid.uuid4()
    provider = FakeProvider(fixture="hotdog")

    outcome = await classify_image(
        db_session,
        provider,
        org,
        user,
        subject_id,
        JPEG,
        question_label="hot dog",
        settings=settings,
    )

    assert outcome.result.verdict == "match"
    assert outcome.result.confidence == 0.97
    assert outcome.cost_usd == Decimal("0.0038")
    assert outcome.latency_ms >= 0
    (request,) = provider.requests
    assert request.model == settings.LLM_MODEL
    assert request.tool_name == TOOL_NAME
    assert "food compliance classifier" in request.system
    assert request.tool_schema["additionalProperties"] is False
    assert set(request.tool_schema["required"]) == {
        "verdict",
        "confidence",
        "observations",
    }
    assert "maximum" not in request.tool_schema["properties"]["confidence"]
    (image,) = request.images
    assert image.media_type == "image/jpeg"
    assert base64.b64decode(image.data_base64) == JPEG
    (row,) = await stored_calls(db_session, subject_id)
    assert row["id"] == outcome.llm_call_id
    assert (row["org_id"], row["user_id"]) == (org, user)
    assert (row["prompt_name"], row["prompt_version"]) == ("classify", 2)
    assert row["status"] == "succeeded"
    assert (row["input_tokens"], row["output_tokens"]) == (1600, 60)
    assert row["cost_usd"] == Decimal("0.0038")
    assert row["result"]["verdict"] == "match"
    assert row["finished_at"] >= row["created_at"]


async def test_the_question_goes_in_the_user_turn_as_data(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    org, user = owner
    provider = FakeProvider(fixture="hotdog")

    await classify_image(
        db_session,
        provider,
        org,
        user,
        uuid.uuid4(),
        JPEG,
        question_label="pizza slice",
        settings=settings,
    )

    (request,) = provider.requests
    # The label is data in the user turn, inside the tags, and nowhere else.
    assert "pizza slice" not in request.system
    assert "<subject>" in request.system
    assert request.user.startswith("<subject>pizza slice</subject>\n")
    assert request.user.count("pizza slice") == 1
    assert "{" not in request.user


async def test_invalid_output_records_a_row_per_attempt_then_raises(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    org, user = owner
    subject_id = uuid.uuid4()
    provider = FakeProvider(fixture="hotdog_invalid")

    with pytest.raises(LLMOutputError):
        await classify_image(
            db_session,
            provider,
            org,
            user,
            subject_id,
            JPEG,
            question_label="hot dog",
            settings=settings,
        )

    rows = await stored_calls(db_session, subject_id)
    assert [row["status"] for row in rows] == ["invalid_output", "invalid_output"]
    assert all("sausage" in row["error"] for row in rows)
    assert all(row["cost_usd"] > 0 for row in rows)


async def test_a_second_attempt_that_validates_sums_the_cost(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    org, user = owner
    subject_id = uuid.uuid4()
    provider = FakeProvider(fixture="hotdog")
    provider.queue = ["hotdog_invalid"]

    outcome = await classify_image(
        db_session,
        provider,
        org,
        user,
        subject_id,
        JPEG,
        question_label="hot dog",
        settings=settings,
    )

    rows = await stored_calls(db_session, subject_id)
    assert [row["status"] for row in rows] == ["invalid_output", "succeeded"]
    assert outcome.llm_call_id == rows[1]["id"]
    assert outcome.cost_usd == sum(row["cost_usd"] for row in rows)


async def test_a_cancelled_second_attempt_keeps_the_first_row(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    """arq cancels at job_timeout. The rows of finished attempts stay."""
    org, user = owner
    subject_id = uuid.uuid4()
    provider = FakeProvider(fixture="hotdog_invalid")
    real_stream = provider.stream

    def stream(request: Any) -> Any:
        if len(provider.requests) == 1:
            raise asyncio.CancelledError
        return real_stream(request)

    provider.stream = stream  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(asyncio.CancelledError):
        await classify_image(
            db_session,
            provider,
            org,
            user,
            subject_id,
            JPEG,
            question_label="hot dog",
            settings=settings,
        )

    rows = await stored_calls(db_session, subject_id)
    assert [row["status"] for row in rows] == ["invalid_output"]


async def test_an_input_over_the_byte_cap_is_refused_before_the_call(
    db_session: AsyncSession, settings: Settings, owner: Owner
) -> None:
    org, user = owner
    subject_id = uuid.uuid4()
    provider = FakeProvider(fixture="hotdog")
    too_big = b"x" * (settings.LLM_MAX_IMAGE_BYTES + 1)

    with pytest.raises(InputTooLargeError):
        await classify_image(
            db_session,
            provider,
            org,
            user,
            subject_id,
            too_big,
            question_label="hot dog",
            settings=settings,
        )

    assert provider.requests == []
    assert await stored_calls(db_session, subject_id) == []
