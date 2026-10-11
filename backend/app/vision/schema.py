"""The vision tool: the Pydantic model that validates it and its JSON schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["match", "no_match"]

# Keys a strict tool schema rejects. The model validates them after the call.
UNSUPPORTED_SCHEMA_KEYS = frozenset({"minimum", "maximum", "minLength", "maxLength"})


class VisionResult(BaseModel):
    # extra="forbid" puts `additionalProperties: false` in the schema.
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict = Field(
        description="match when the asked item is visible, else no_match."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Certainty of the verdict, from 0 to 1."
    )
    observations: str = Field(
        max_length=300,
        description="One sentence under 300 characters about what is visible.",
    )


def tool_schema() -> dict[str, Any]:
    """The input schema of the tool, without the keys strict mode rejects."""
    schema: dict[str, Any] = VisionResult.model_json_schema()
    schema.pop("title", None)
    properties: dict[str, dict[str, Any]] = schema["properties"]
    schema["properties"] = {
        name: {
            key: value
            for key, value in field.items()
            if key not in UNSUPPORTED_SCHEMA_KEYS
        }
        for name, field in properties.items()
    }
    return schema
