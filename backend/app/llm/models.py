"""One row per LLM call. Written before the call starts, updated when it ends."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.repository import OrgScoped, Repository


class CallStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    # The model answered, but the tool input did not validate.
    invalid_output = "invalid_output"


def _now() -> datetime:
    return datetime.now(UTC)


class LLMCall(OrgScoped):
    __tablename__ = "llm_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # The row the call is about. No foreign key: each feature names its own table.
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    request_id: Mapped[str] = mapped_column(String(128))
    prompt_name: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, native_enum=False, create_constraint=True, length=16)
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    error: Mapped[str | None] = mapped_column(Text)
    # Set in Python, so two calls in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LLMCallRepository(Repository[LLMCall]):
    model = LLMCall
