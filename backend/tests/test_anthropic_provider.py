"""The real provider against a replayed SSE wire stream. No network."""

import json
from dataclasses import replace
from typing import Any

import httpx2
from anthropic import DefaultAsyncHttpxClient

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.provider import (
    Error,
    ImageInput,
    LLMEvent,
    LLMRequest,
    TextDelta,
    ToolInput,
    Usage,
)

# Copied from the streaming page of the Claude docs, "Streaming request with
# tool use", with the tool renamed. Each event is one SSE frame.
WIRE_EVENTS = [
    (
        "message_start",
        '{"type":"message_start","message":{"id":"msg_014p7gG3wDgGV9EUtLvnow3U",'
        '"type":"message","role":"assistant","model":"claude-sonnet-5-5",'
        '"stop_sequence":null,"usage":{"input_tokens":472,"output_tokens":2},'
        '"content":[],"stop_reason":null}}',
    ),
    (
        "content_block_start",
        '{"type":"content_block_start","index":0,'
        '"content_block":{"type":"text","text":""}}',
    ),
    ("ping", '{"type": "ping"}'),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":"Okay"}}',
    ),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":", summarizing:"}}',
    ),
    ("content_block_stop", '{"type":"content_block_stop","index":0}'),
    (
        "content_block_start",
        '{"type":"content_block_start","index":1,"content_block":{"type":"tool_use",'
        '"id":"toolu_01T1x1fJ34qAmk2tNTrN7Up6","name":"note_summary","input":{}}}',
    ),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":1,'
        '"delta":{"type":"input_json_delta","partial_json":""}}',
    ),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":1,'
        '"delta":{"type":"input_json_delta","partial_json":"{\\"summary\\":"}}',
    ),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta",'
        '"partial_json":" \\"Ship on Friday.\\", \\"tags\\": [\\"rele"}}',
    ),
    (
        "content_block_delta",
        '{"type":"content_block_delta","index":1,'
        '"delta":{"type":"input_json_delta","partial_json":"ase\\"]}"}}',
    ),
    ("content_block_stop", '{"type":"content_block_stop","index":1}'),
    (
        "message_delta",
        '{"type":"message_delta","delta":{"stop_reason":"tool_use",'
        '"stop_sequence":null},"usage":{"output_tokens":89}}',
    ),
    ("message_stop", '{"type":"message_stop"}'),
]

REQUEST = LLMRequest(
    model="claude-sonnet-5-5",
    max_output_tokens=256,
    system="Summarize the note with the note_summary tool.",
    user="Title: Plan\n\nShip on Friday.",
    tool_name="note_summary",
    tool_description="Record the summary.",
    tool_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "tags"],
        "additionalProperties": False,
    },
)


def wire(events: list[tuple[str, str]]) -> bytes:
    return "".join(f"event: {name}\ndata: {data}\n\n" for name, data in events).encode()


def provider_with(
    handler: Any, max_retries: int = 0, timeout: float = 5.0
) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="sk-ant-test",
        timeout=timeout,
        max_retries=max_retries,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )


async def collect(
    provider: AnthropicProvider, request: LLMRequest = REQUEST
) -> list[LLMEvent]:
    return [event async for event in provider.stream(request)]


async def test_valid_stream_parses_text_tool_input_and_usage() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=wire(WIRE_EVENTS),
        )

    events = await collect(provider_with(handler))

    assert [e.text for e in events if isinstance(e, TextDelta)] == [
        "Okay",
        ", summarizing:",
    ]
    assert [e for e in events if isinstance(e, ToolInput)] == [
        ToolInput(input={"summary": "Ship on Friday.", "tags": ["release"]})
    ]
    assert events[-1] == Usage(
        input_tokens=472, output_tokens=89, stop_reason="tool_use"
    )
    (body,) = sent
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 256
    assert body["stream"] is True
    assert body["tool_choice"] == {"type": "auto"}
    assert body["tools"][0]["name"] == "note_summary"
    assert body["tools"][0]["strict"] is True
    assert body["tools"][0]["input_schema"] == REQUEST.tool_schema
    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": REQUEST.user}]}
    ]


async def test_images_go_before_the_text_as_base64_blocks() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=wire(WIRE_EVENTS),
        )

    image = ImageInput(media_type="image/jpeg", data_base64="/9j/4AAQ")
    request = replace(REQUEST, images=[image])

    events = await collect(provider_with(handler), request)

    assert isinstance(events[-1], Usage)
    (body,) = sent
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": "/9j/4AAQ",
                    },
                },
                {"type": "text", "text": REQUEST.user},
            ],
        }
    ]


async def test_interrupted_stream_ends_with_a_provider_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=wire(WIRE_EVENTS[:5]),
        )

    events = await collect(provider_with(handler))

    assert [e.text for e in events if isinstance(e, TextDelta)] == [
        "Okay",
        ", summarizing:",
    ]
    assert isinstance(events[-1], Error)
    assert events[-1].code == "provider_error"
    assert not any(isinstance(e, Usage | ToolInput) for e in events)


async def test_timeout_ends_with_a_timeout_error_after_the_retries() -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.ReadTimeout("read timed out", request=request)

    events = await collect(provider_with(handler, max_retries=1))

    assert len(events) == 1
    assert isinstance(events[0], Error)
    assert events[0].code == "timeout"
    assert attempts == 2


async def test_api_error_ends_with_a_provider_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            529,
            headers={"content-type": "application/json"},
            json={
                "type": "error",
                "error": {"type": "overloaded_error", "message": "x"},
            },
        )

    events = await collect(provider_with(handler))

    assert len(events) == 1
    assert isinstance(events[0], Error)
    assert events[0].code == "provider_error"
