.PHONY: setup dev serve-backend serve-frontend serve-worker check drift generate down

# Create local config and install all packages. Installs run only when the
# lock files change. Safe to run again.
setup: backend/.venv/.stamp frontend/node_modules/.stamp .railway/node_modules/.stamp
	test -f .env || cp .env.example .env
	test -f frontend/.env || cp frontend/.env.example frontend/.env

backend/.venv/.stamp: backend/pyproject.toml backend/uv.lock
	cd backend && uv sync --locked
	touch $@

frontend/node_modules/.stamp: frontend/package-lock.json
	cd frontend && npm ci
	touch $@

.railway/node_modules/.stamp: .railway/package-lock.json
	cd .railway && npm ci
	touch $@

# One command from a fresh clone to a running app. Ctrl-C stops all three
# processes.
dev: setup
	docker compose up -d --wait
	$(MAKE) -C backend migrate
	$(MAKE) -C backend seed
	$(MAKE) -j3 serve-backend serve-frontend serve-worker

serve-backend:
	$(MAKE) -C backend serve

serve-frontend:
	cd frontend && npm run dev

serve-worker:
	$(MAKE) -C backend worker

# Everything the checks cover. Needs Compose up.
check:
	$(MAKE) -C backend check
	cd frontend && npm run check
	frontend/node_modules/.bin/tsc --noEmit --strict --module nodenext --target es2022 .railway/railway.ts
	$(MAKE) drift

# Regenerate the spec from the code and the client from the committed spec
# into a temporary directory, then compare with the committed files. Never
# writes into the repo. The client reads the committed spec because the
# generator derives a type from the input path.
drift:
	tmp=$$(mktemp -d) || exit 1; trap 'rm -rf "$$tmp"' EXIT; \
	$(MAKE) -C backend openapi OPENAPI_OUT="$$tmp/openapi.json" && \
	( cd frontend && OPENAPI_TS_OUTPUT="$$tmp/api" npm run generate -- --no-log-file ) && \
	diff -u frontend/openapi.json "$$tmp/openapi.json" && \
	diff -ru frontend/src/lib/api "$$tmp/api" || \
	{ echo "error: openapi.json or the generated client is out of date. Run make generate."; exit 1; }

generate:
	$(MAKE) -C backend openapi
	cd frontend && npm run generate

down:
	docker compose down
