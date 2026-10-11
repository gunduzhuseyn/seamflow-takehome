# Testing

## Context

The agent writes code and tests; the owner does not read every test. Generated
tests reproduce the implementation's mistakes, and passing tests can miss
requested behaviour (arXiv 2508.00408, 2606.28430; Böckeler 2026-08,
martinfowler.com). Risks: a query that forgets `org_id`, a skipped error path,
invalid LLM output.

## Decision

Few acceptance tests at the API boundary, derived from the requirement text
before the code, plus unit tests for pure logic. No coverage target.

**Backend, tested**
- Routes through `httpx.AsyncClient` with `ASGITransport` on real Postgres: one
  happy path and the error paths 401, 403, 404, 422. The client fixture enters
  the app lifespan, which `ASGITransport` skips.
- Tenancy: seed two orgs with overlapping data. For every table with an
  `org_id` column, from table metadata: A lists and reads its own records; A's
  list hides B; get, update, delete, and the LLM action on B's record return
  404 and leave B's row unchanged. One denied-role case uses the real
  authorization dependency.
- Migrations: `alembic upgrade head` on an empty database once per session,
  `alembic check`, one test that asserts a single head.
- Jobs: the unit case calls the job function with a hand-built context. Run a
  job twice and assert one persisted effect. One burst-worker test with
  `Worker.run_check` on real Redis covers retry and final failure.
- LLM: a fake provider implements our interface and yields events from JSON
  fixtures: valid, invalid JSON, refusal, max_tokens. Tests assert stored
  result, failure state, event order, request limits. One adapter test injects
  the SDK `http_client`: valid parses, interrupted fails.
- Settings loads from a full env and fails on a missing variable.

**Backend, skipped**
- Mocked repositories and repository unit tests. Routes cover them.
- Downgrade tests. Platform rollback never runs downgrade.
- A populated previous-revision migration test. Compatibility is a review rule.
- A concurrent duplicate-job race test. The unique constraint is the guard.
- HTTP cassettes. Fixtures do the job with no dependency.
- Live calls and the smoke script sit behind markers `live` and `smoke`.

**Frontend**
- `tsc --noEmit` strict over the generated client is the main check.
- Vitest, jsdom, Testing Library: form validation, list loading, empty and
  error states, polling with fake timers. MSW handlers typed
  with generated response types are the only seam; the real client and cache
  run.
- Skipped: Playwright, snapshots, Storybook, Vitest browser mode; the build and
  the smoke script cover them. Before you hand the app over, a two-minute
  manual click-through of the deployed UI, since nothing automated runs in a
  browser.

## Tools, local simulation, check command

Backend: pytest, pytest-asyncio in auto mode, httpx, fakeredis, ruff, pyright.
Frontend: Vitest, Testing Library, jsdom, MSW 3, ESLint 10, typescript-eslint,
Prettier. Postgres from Compose, locally and in CI; tests use
`TEST_DATABASE_URL`, never the development `DATABASE_URL`. Migrate once per
session; each test gets one connection and an outer transaction joined with
`create_savepoint`, rolled back on teardown. Redis: fakeredis, plus real Redis
for the burst-worker test. Storage: the filesystem adapter; the S3 adapter runs
once against RustFS, from Compose, locally and in CI. LLM:
the fake provider, plus a conftest guard that fails any test that reaches a
host other than Postgres, Redis, or RustFS.

`make check` in `backend/` runs `uv run ruff format --check`, `uv run ruff
check`, `uv run pyright`, `uv run alembic check`, and `uv run pytest` with
`addopts = -m "not live and not smoke"`. The backend has no build step; the CI
Docker build is its equivalent. `npm run check` in `frontend/` chains lint,
typecheck, test, and build with `&&`. CI runs both.

## Adding tests per feature

- Acceptance tests are derived from the requirement text in their own turn,
  before any code, and committed separately with the failing run pasted. The
  implementing turn does not edit `tests/acceptance/`.
- Red before green is the evidence. Each acceptance test fails once against the
  empty route and passes after. Both runs are pasted.
- The cold reviewer (Codex) reads the test diff with one brief: does each test
  assert the stored outcome, not only a status code, and was any acceptance
  test weakened. The owner reads only that diff.
- One fault drill in the skeleton unit: remove the `org_id` filter in one
  query, run the check, confirm the tenancy tests fail, record it.
