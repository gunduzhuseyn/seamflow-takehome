"""LLMProvider that replays a JSON fixture. Tests and LLM_PROVIDER=fake use it.

A fixture is a list of events: `{"type": "text", "text"}`,
`{"type": "tool_input", "input"}`, `{"type": "usage", "input_tokens",
"output_tokens", "stop_reason"}`, or `{"type": "error", "code", "message"}`.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.llm.provider import Error, LLMEvent, LLMRequest, TextDelta, ToolInput, Usage

# backend/app/llm/fake_provider.py -> backend/tests/fixtures/llm
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "llm"


def _event(raw: dict[str, Any]) -> LLMEvent:
    kind = raw["type"]
    if kind == "text":
        return TextDelta(text=raw["text"])
    if kind == "tool_input":
        return ToolInput(input=raw["input"])
    if kind == "usage":
        return Usage(
            input_tokens=raw["input_tokens"],
            output_tokens=raw["output_tokens"],
            stop_reason=raw["stop_reason"],
        )
    if kind == "error":
        return Error(code=raw["code"], message=raw["message"])
    raise ValueError(f"unknown fixture event type {kind!r}")


class FakeProvider:
    """Replays `fixture` from `fixtures_dir`. Records every request."""

    def __init__(
        self, fixtures_dir: Path = FIXTURES_DIR, fixture: str = "valid"
    ) -> None:
        self.fixtures_dir = fixtures_dir
        self.fixture = fixture
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.requests.append(request)
        raw: list[dict[str, Any]] = json.loads(
            (self.fixtures_dir / f"{self.fixture}.json").read_text()
        )
        for item in raw:
            yield _event(item)
