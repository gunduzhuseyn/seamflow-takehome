"""The API shape of one `llm_calls` row. `app.llm.complete` runs the call."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.llm.models import CallStatus


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
