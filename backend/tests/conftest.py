import asyncio
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jwt
import pytest
from alembic import command
from alembic.config import Config
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.constants import (
    health_check_key_suffix,
    in_progress_key_prefix,
    job_key_prefix,
    result_key_prefix,
    retry_key_prefix,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.clerk import get_clerk
from app.core.config import Settings
from app.core.db import create_engine, get_session, get_stream_session
from app.llm.fake_provider import FakeProvider
from app.main import create_app
from app.storage.client import get_storage
from tests.fakes import FakeClerk, FakeStorage, TokenFactory

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR.parent / ".env"

# Only `pytest -m live` reaches it.
LLM_HOST = "api.anthropic.com"

# The only authorized party in test settings. Tokens carry it as `azp`.
AUTHORIZED_PARTY = "http://localhost:5173"
ISSUER = "https://test.clerk.accounts.dev"


class _TestEnv(BaseSettings):
    """Reads the test-only variable. The app Settings never sees it."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    TEST_DATABASE_URL: str


def _database_identity(url: str) -> tuple[str | None, int | None, str]:
    parts = urlparse(url)
    return parts.hostname, parts.port, parts.path


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    """Signs test session tokens. Its public key goes into the test settings."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


@pytest.fixture(scope="session")
def settings(signing_key: rsa.RSAPrivateKey) -> Settings:
    development = Settings()  # pyright: ignore[reportCallIssue]
    test_env = _TestEnv()  # pyright: ignore[reportCallIssue]
    test_url = test_env.TEST_DATABASE_URL
    if _database_identity(test_url) == _database_identity(development.DATABASE_URL):
        pytest.fail(
            "TEST_DATABASE_URL points at the development database. "
            "Tests drop its schema. Use a separate database."
        )
    return Settings(  # pyright: ignore[reportCallIssue]
        DATABASE_URL=test_url,
        CLERK_JWT_KEY=_public_pem(signing_key),
        CLERK_AUTHORIZED_PARTIES=[AUTHORIZED_PARTY],
        # Fixed values, so tests do not depend on the seed values in .env.
        SEED_USER_EMAIL="seed-user+clerk_test@example.com",
        SEED_USER_PASSWORD="test-seed-password",
        ANTHROPIC_API_KEY="sk-ant-test",
        LLM_PROVIDER="fake",
        # Fixed, so a test can count on it.
        LLM_RATE_LIMIT_PER_MINUTE=3,
        # One queue per test run, so parallel runs on one Redis do not collide.
        WORKER_QUEUE_NAME=f"arq:queue:test:{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture(scope="session")
def make_token(signing_key: rsa.RSAPrivateKey) -> TokenFactory:
    """Build a Clerk-shaped session token. Keyword arguments change one part."""

    def make(
        sub: str,
        *,
        azp: str = AUTHORIZED_PARTY,
        expires_in: timedelta = timedelta(minutes=1),
        key: rsa.RSAPrivateKey | None = None,
    ) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": sub,
            "sid": f"sess_{sub}",
            "iss": ISSUER,
            "azp": azp,
            "iat": now,
            "nbf": now - timedelta(seconds=10),
            "exp": now + expires_in,
        }
        return jwt.encode(claims, key or signing_key, algorithm="RS256")

    return make


@pytest.fixture
def fake_clerk() -> FakeClerk:
    return FakeClerk()


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture(scope="session")
def alembic_config(settings: Settings) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(settings)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def arq_pool(settings: Settings) -> AsyncIterator[ArqRedis]:
    """arq connection on this run's queue. Teardown deletes only this run's keys."""
    pool = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL),
        default_queue_name=settings.WORKER_QUEUE_NAME,
    )
    yield pool
    queue = settings.WORKER_QUEUE_NAME
    job_ids: list[Any] = await pool.zrange(queue, 0, -1)  # pyright: ignore[reportUnknownMemberType]
    keys = [queue, queue + health_check_key_suffix]
    for job_id in job_ids:
        name = job_id.decode() if isinstance(job_id, bytes) else str(job_id)
        for prefix in (
            job_key_prefix,
            in_progress_key_prefix,
            retry_key_prefix,
            result_key_prefix,
        ):
            keys.append(f"{prefix}{name}")
    await pool.delete(*keys)
    await pool.aclose()


@pytest.fixture(scope="session")
async def migrated_database(engine: AsyncEngine, alembic_config: Config) -> None:
    """Empty the test database, then run every migration once per session."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await asyncio.to_thread(command.upgrade, alembic_config, "head")


@pytest.fixture
async def db_connection(
    engine: AsyncEngine, migrated_database: None
) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as session:
        yield session


@pytest.fixture
def app(
    settings: Settings,
    db_session: AsyncSession,
    fake_clerk: FakeClerk,
    fake_storage: FakeStorage,
) -> FastAPI:
    app = create_app(settings)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_stream_session] = override_get_session
    app.dependency_overrides[get_clerk] = lambda: fake_clerk
    app.dependency_overrides[get_storage] = lambda: fake_storage
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def fake_llm(app: FastAPI, client: AsyncClient) -> FakeProvider:
    """The provider the lifespan built from LLM_PROVIDER=fake."""
    provider = app.state.llm_provider
    assert isinstance(provider, FakeProvider)
    return provider


@pytest.fixture(scope="session", autouse=True)
def network_guard(settings: Settings, request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail any test that opens a socket to a host outside the Compose services."""
    hosts = {"localhost", "127.0.0.1", "::1"}
    if request.config.getoption("-m") == "live":
        hosts.add(LLM_HOST)
    for url in (
        settings.DATABASE_URL,
        settings.REDIS_URL,
        settings.STORAGE_ENDPOINT_URL,
        settings.STORAGE_PUBLIC_ENDPOINT_URL,
    ):
        hostname = urlparse(url).hostname
        if hostname:
            hosts.add(hostname)
    allowed: set[str] = set(hosts)
    for host in hosts:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            continue
        for info in infos:
            allowed.add(str(info[4][0]))

    def check(sock: socket.socket, address: tuple[Any, ...] | str | bytes) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = str(address[0]) if isinstance(address, tuple) else str(address)
            if host not in allowed:
                raise RuntimeError(f"test reached network host {host}")

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(
        self: socket.socket, address: tuple[Any, ...] | str | bytes
    ) -> None:
        check(self, address)
        real_connect(self, address)

    def guarded_connect_ex(
        self: socket.socket, address: tuple[Any, ...] | str | bytes
    ) -> int:
        check(self, address)
        return real_connect_ex(self, address)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", guarded_connect)
        mp.setattr(socket.socket, "connect_ex", guarded_connect_ex)
        yield
