from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    CLERK_JWT_KEY,
    PLACEHOLDERS,
    Environment,
    LLMProviderName,
    Settings,
)

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_settings_loads_from_complete_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example, https://www.example")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_real")
    monkeypatch.setenv("SEED_USER_EMAIL", "owner@app.example")
    monkeypatch.setenv("SEED_USER_PASSWORD", "a-real-password")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.ENVIRONMENT is Environment.production
    assert settings.DATABASE_URL == "postgresql+asyncpg://u:p@db:5432/app"
    assert settings.REDIS_URL == "redis://cache:6379/0"
    assert settings.CORS_ORIGINS == ["https://app.example", "https://www.example"]
    assert settings.CLERK_AUTHORIZED_PARTIES == settings.CORS_ORIGINS
    assert settings.CLERK_SECRET_KEY == "sk_test_real"
    assert settings.ANTHROPIC_API_KEY == "sk-ant-real"
    assert settings.LLM_PROVIDER is LLMProviderName.anthropic
    assert settings.LLM_MODEL == "claude-sonnet-5-5"
    assert settings.LLM_MAX_OUTPUT_TOKENS > 0
    assert settings.LLM_INPUT_TOKEN_LIMIT > 0
    assert settings.LLM_RATE_LIMIT_PER_MINUTE > 0
    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert settings.LLM_MAX_RETRIES >= 0


def test_settings_fails_on_missing_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert exc_info.value.errors()[0]["loc"] == ("DATABASE_URL",)


def _example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def test_placeholders_match_env_example() -> None:
    example = _example_values()
    in_settings = {k: v for k, v in example.items() if k in Settings.model_fields}

    assert in_settings == PLACEHOLDERS


def test_production_rejects_placeholder_value(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _example_values().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")
    monkeypatch.setenv("SEED_USER_EMAIL", "owner@app.example")
    monkeypatch.setenv("SEED_USER_PASSWORD", "a-real-password")

    with pytest.raises(ValidationError, match="CLERK_SECRET_KEY") as exc_info:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    # The error names the variable. It never prints a value, which is a
    # secret in production.
    assert PLACEHOLDERS["CLERK_SECRET_KEY"] not in str(exc_info.value)
    assert "input_value" not in str(exc_info.value)


def _set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "REDIS_URL",
        "CLERK_SECRET_KEY",
        "SEED_USER_EMAIL",
        "SEED_USER_PASSWORD",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.setenv(name, "x")


def test_production_requires_the_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LLM_PROVIDER", "fake")

    with pytest.raises(ValidationError, match="LLM_PROVIDER"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_jwt_key_with_escaped_newlines_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv("CLERK_JWT_KEY", CLERK_JWT_KEY.replace("\n", "\\n"))

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.CLERK_JWT_KEY == CLERK_JWT_KEY


def test_jwt_key_that_is_not_a_pem_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv("CLERK_JWT_KEY", "not a key")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert exc_info.value.errors()[0]["loc"] == ("CLERK_JWT_KEY",)
