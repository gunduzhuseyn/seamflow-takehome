# Build stage: install locked runtime dependencies into /app/.venv.
FROM ghcr.io/astral-sh/uv:0.13.0-python3.14-trixie-slim AS builder

# No RUN --mount: Railway rejects bind mounts, and cache mounts without a
# service-specific id. COPY the lock files instead.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# Runtime stage: the same Python base as the build stage, without uv.
FROM python:3.14.8-slim-trixie

RUN useradd --system --user-group --no-create-home app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
