"""The provider interface. One structured call streams a sequence of events."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from fastapi import Request

# Why a call did not give a usable result. The browser shows one state per code.
ErrorCode = Literal[
    "invalid_output", "refusal", "max_tokens", "provider_error", "timeout"
]


ImageMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]


@dataclass(frozen=True)
class ImageInput:
    """One image in the user turn, base64 without newlines."""

    media_type: ImageMediaType
    data_base64: str


@dataclass(frozen=True)
class LLMRequest:
    model: str
    max_output_tokens: int
    system: str
    user: str
    # The one tool the model calls. Its input is the structured output.
    tool_name: str
    tool_description: str
    tool_schema: dict[str, Any]
    # Sent before the user text.
    images: list[ImageInput] = field(default_factory=list[ImageInput])


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolInput:
    """The final tool input, parsed. Validate it before use."""

    input: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """The last event of a completed call."""

    input_tokens: int
    output_tokens: int
    stop_reason: str


@dataclass(frozen=True)
class Error:
    """The last event of a call that did not complete."""

    code: ErrorCode
    message: str


LLMEvent = TextDelta | ToolInput | Usage | Error


class LLMProvider(Protocol):
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Yield text deltas, then the tool input and usage, or an error."""
        ...


def get_provider(request: Request) -> LLMProvider:
    """The provider the lifespan built from LLM_PROVIDER."""
    return request.app.state.llm_provider
