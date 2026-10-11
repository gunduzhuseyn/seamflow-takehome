.PHONY: dev migrate seed serve worker check env openapi storage-init

ALEMBIC = uv run --env-file ../.env alembic
# The root drift check overrides this with a temporary path.
OPENAPI_OUT ?= ../frontend/openapi.json

env:
	test -f ../.env || cp ../.env.example ../.env

migrate: env
	$(ALEMBIC) upgrade head

# Idempotent. Creates the demo org and the seed user, in Clerk too.
seed: env
	uv run --env-file ../.env python -m app.seed

serve:
	uv run uvicorn app.main:app --reload --port 8000

# Create the bucket and its CORS rule in the local object store. Development only.
storage-init: env
	uv run --env-file ../.env python -m app.storage

# The arq worker. It reads the same .env as the API.
worker:
	uv run arq app.worker.WorkerSettings

dev: migrate seed
	$(MAKE) serve

check: migrate
	uv run ruff format --check
	uv run ruff check
	uv run pyright
	$(ALEMBIC) check
	uv run pytest

# Dump the OpenAPI document for the frontend client generator.
openapi: env
	uv run --env-file ../.env python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > $(OPENAPI_OUT)
