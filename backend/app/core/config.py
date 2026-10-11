from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py -> repository root
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

# The values in .env.example. A production setting with one of these values
# is a copy that was never configured. tests/test_settings.py keeps this
# dictionary equal to the file.
PLACEHOLDERS = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgresql+asyncpg://app:app@localhost:5432/app",
    "REDIS_URL": "redis://localhost:6379/0",
    "CORS_ORIGINS": "http://localhost:5173",
    "CLERK_SECRET_KEY": "sk_test_replace_me",
    "SEED_USER_EMAIL": "replace-me+clerk_test@example.com",
    "SEED_USER_PASSWORD": "replace-me-with-a-long-password",
    "ANTHROPIC_API_KEY": "sk-ant-replace_me",
    "STORAGE_ENDPOINT_URL": "http://localhost:9000",
    "STORAGE_ACCESS_KEY_ID": "rustfsadmin",
    "STORAGE_SECRET_ACCESS_KEY": "rustfsadmin",
}

# The shared Clerk development instance. Both values are public.
CLERK_PUBLISHABLE_KEY = "pk_test_c2FmZS1zdGluZ3JheS0zOTczLmNsZXJrLmFjY291bnRzLmRldiQ"
CLERK_JWT_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtghGPPnMccb9wRiI99rc
39l49qGIN9MOl33V9z75CCVrq1RJXrX2cFEG65lKSUfJY8QJ1m6kP/w8BcO2WQ9j
v2Bh74MorhzJW/WCI7ZcZIa1OYYXmQ6F0L+wTgElx898XRwD+oSy6mGom+yhSMJo
SH7M3xlD0S/odj8tqwScefGSMcmVirgzKMTYaIY8JIJGh2rHGP6QEYqbwWqWAXBP
n1HVhCdUVJJ6jbqww+fQulMgsVZzZPq1FZbGCQBmDz7tSOi70yqzuIvOAQ2X3PH+
4lZkOuw+0BsFQ615dHBBIKs714tdnFbLf5379skR5+uqeePSTr8rgjjxhjC/FmAG
1QIDAQAB
-----END PUBLIC KEY-----
"""


class Environment(StrEnum):
    development = "development"
    production = "production"


class LogFormat(StrEnum):
    json = "json"
    text = "text"


class LLMProviderName(StrEnum):
    anthropic = "anthropic"
    # Replays tests/fixtures/llm/*.json. Never in production.
    fake = "fake"


def _split_commas(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class LoggingSettings(BaseSettings):
    """The settings that logging needs. The Alembic env reads only these."""

    # hide_input_in_errors: a validation error names the field, not the value.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, extra="ignore", hide_input_in_errors=True
    )

    ENVIRONMENT: Environment = Environment.development
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Default: json in production, text in development.
    LOG_FORMAT: LogFormat = LogFormat.text

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def upper_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def default_log_format(self) -> Self:
        if "LOG_FORMAT" not in self.model_fields_set:
            production = self.ENVIRONMENT is Environment.production
            log_format = LogFormat.json if production else LogFormat.text
            # setattr: pyright reads an uppercase attribute as a constant.
            setattr(self, "LOG_FORMAT", log_format)  # noqa: B010
        return self


class Settings(LoggingSettings):
    DATABASE_URL: str
    REDIS_URL: str
    # Comma-separated in the environment. NoDecode turns off JSON parsing.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    CLERK_PUBLISHABLE_KEY: str = CLERK_PUBLISHABLE_KEY
    # PEM. One environment line carries it with each newline written as \n.
    CLERK_JWT_KEY: str = CLERK_JWT_KEY
    CLERK_SECRET_KEY: str
    # Allowed `azp` values of a session token. Default: CORS_ORIGINS.
    CLERK_AUTHORIZED_PARTIES: Annotated[list[str], NoDecode] = []
    SEED_USER_EMAIL: str
    SEED_USER_PASSWORD: str

    ANTHROPIC_API_KEY: str
    LLM_PROVIDER: LLMProviderName = LLMProviderName.anthropic
    LLM_MODEL: str = "claude-sonnet-5-5"
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    # Largest model input, in bytes, after the resize.
    LLM_MAX_IMAGE_BYTES: int = 2 * 1024 * 1024
    # Per user, counted in Redis.
    LLM_RATE_LIMIT_PER_MINUTE: int = 10
    # One attempt. The SDK retries that many more times on 408, 409, 429,
    # 5xx, and connection errors.
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 2

    # Object storage through the S3 API: RustFS in Compose, Cloudflare R2 live.
    STORAGE_ENDPOINT_URL: str
    # The endpoint the browser reaches. Only presigned URLs carry it.
    # Default: STORAGE_ENDPOINT_URL.
    STORAGE_PUBLIC_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY_ID: str
    STORAGE_SECRET_ACCESS_KEY: str
    STORAGE_BUCKET: str = "seamflow-takehome"
    STORAGE_REGION: str = "auto"

    # Runs of one job before it is failed. Stored on the job row at enqueue.
    WORKER_MAX_ATTEMPTS: int = 3
    WORKER_JOB_TIMEOUT_SECONDS: int = 60
    # The arq queue key. Tests set one name per run.
    WORKER_QUEUE_NAME: str = "arq:queue"

    @field_validator("CORS_ORIGINS", "CLERK_AUTHORIZED_PARTIES", mode="before")
    @classmethod
    def split_lists(cls, value: object) -> object:
        return _split_commas(value)

    @field_validator("CLERK_JWT_KEY")
    @classmethod
    def parse_pem(cls, value: str) -> str:
        pem = value.replace("\\n", "\n")
        load_pem_public_key(pem.encode())
        return pem

    @model_validator(mode="after")
    def check_settings(self) -> Self:
        if "CLERK_AUTHORIZED_PARTIES" not in self.model_fields_set:
            # setattr: pyright reads an uppercase attribute as a constant.
            setattr(self, "CLERK_AUTHORIZED_PARTIES", list(self.CORS_ORIGINS))  # noqa: B010
        if not self.STORAGE_PUBLIC_ENDPOINT_URL:
            setattr(self, "STORAGE_PUBLIC_ENDPOINT_URL", self.STORAGE_ENDPOINT_URL)  # noqa: B010
        if self.ENVIRONMENT is Environment.production:
            if self.LLM_PROVIDER is not LLMProviderName.anthropic:
                raise ValueError("LLM_PROVIDER must be anthropic in production.")
            for name, placeholder in PLACEHOLDERS.items():
                value = getattr(self, name)
                if isinstance(value, list):
                    value = ",".join(str(item) for item in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
                if value == placeholder:
                    raise ValueError(
                        f"{name} still has its .env.example value. "
                        "Set it for production."
                    )
        return self
