from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from redis.asyncio import Redis

from app.auth.router import router as auth_router
from app.classifications.router import router as classifications_router
from app.core.access_log import AccessLogMiddleware
from app.core.clerk import ClerkBackend
from app.core.config import LLMProviderName, Settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.health.router import router as health_router
from app.jobs.router import router as jobs_router
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.fake_provider import FakeProvider
from app.llm.provider import LLMProvider
from app.llm.router import router as llm_router
from app.storage.client import S3Storage


def generate_unique_id(route: APIRoute) -> str:
    """Stable operation ids for the generated client: `<tag>-<name>`."""
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings)
    engine = create_engine(settings)
    redis: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.REDIS_URL
    )
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.redis = redis
    # The arq connection. Routes enqueue jobs on it.
    app.state.arq = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL),
        default_queue_name=settings.WORKER_QUEUE_NAME,
    )
    app.state.clerk = ClerkBackend(settings.CLERK_SECRET_KEY)
    app.state.llm_provider = create_llm_provider(settings)
    app.state.storage = S3Storage.from_settings(settings)
    try:
        yield
    finally:
        await app.state.arq.aclose()
        await redis.aclose()
        await engine.dispose()


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.LLM_PROVIDER is LLMProviderName.fake:
        return FakeProvider()
    return AnthropicProvider(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    app = FastAPI(
        title="SeeFood Enterprise",
        lifespan=lifespan,
        generate_unique_id_function=generate_unique_id,
    )
    app.state.settings = settings
    # The last one added runs first. The access log runs inside the request
    # id, so its 500 response carries the id. CORS wraps both.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(classifications_router)
    app.include_router(jobs_router)
    app.include_router(llm_router)
    return app


app = create_app()
