"""LLMProvider on the Anthropic SDK: one streamed message with one tool.

The current models reject a forced `tool_choice`, so the request sends
`auto` with `strict: true` and the prompt names the tool. A reply with no
tool call has no ToolInput event; the caller treats that as invalid output.
"""

from collections.abc import AsyncIterator

import anthropic
from anthropic.types import ContentBlockParam, ImageBlockParam, ToolParam

from app.llm.provider import (
    Error,
    ImageInput,
    LLMEvent,
    LLMRequest,
    TextDelta,
    ToolInput,
    Usage,
)


def _image_block(image: ImageInput) -> ImageBlockParam:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": image.media_type,
            "data": image.data_base64,
        },
    }


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        timeout: float,
        max_retries: int,
        http_client: anthropic.DefaultAsyncHttpxClient | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        tool: ToolParam = {
            "name": request.tool_name,
            "description": request.tool_description,
            "input_schema": request.tool_schema,
            "strict": True,
        }
        # Images first, then the text, as the vision docs show.
        content: list[ContentBlockParam] = [
            _image_block(image) for image in request.images
        ]
        content.append({"type": "text", "text": request.user})
        try:
            async with self._client.messages.stream(
                model=request.model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[{"role": "user", "content": content}],
                tools=[tool],
                tool_choice={"type": "auto"},
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(text=event.text)
                message = await stream.get_final_message()
        except anthropic.APITimeoutError as error:
            yield Error(code="timeout", message=str(error))
            return
        except (anthropic.APIError, ValueError, RuntimeError) as error:
            # APIError: a status or connection failure after the retries.
            # ValueError: tool input JSON the SDK could not parse.
            # RuntimeError: the stream ended before message_stop.
            yield Error(
                code="provider_error", message=f"{type(error).__name__}: {error}"
            )
            return
        if message.stop_reason is None:
            # The connection closed before message_delta. The SDK does not raise.
            yield Error(code="provider_error", message="stream ended early")
            return
        for block in message.content:
            if block.type == "tool_use":
                yield ToolInput(input=dict(block.input))
                break
        yield Usage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason or "end_turn",
        )
