# Reference conventions

## Context

We build from scratch with a fixed stack. Agents need named sources for
layout, settings, database access, migrations, client generation, and
CI, so they do not invent one per session. Checked on 2026-10-10.

## Candidates

| Source | Licence | Last release / commit | Solves for us | Not copied |
| --- | --- | --- | --- | --- |
| [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | MIT | 0.12.0 2026-08-12 / 2026-10-08 | Two-package layout, `SessionDep` and `CurrentUser` deps, settings shape, `prestart` = upgrade head + seed, `generate-client.sh`, client config, CI shape | SQLModel models and CRUD, JWT email auth, email stack, Playwright, TanStack Router, Bun, Biome, FastAPI Cloud deploy, Traefik |
| [polarsource/polar](https://github.com/polarsource/polar) | Apache-2.0 | per-package tags / 2026-10-09 | `MetaData` naming convention and model mixins, generic repository with explicit `organization_id` filters, Alembic `file_template`, single-head check, `test_server.yaml` | Monorepo, 34 workflows, dramatiq, read replicas, 850-line settings |
| [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) | none (cite only) | no releases / 2026-05-03 | Backend layout by domain module, table naming rules, reversible slug-named migrations | Raw-SQL service examples, `requirements/*.txt`, chained-dependency examples |
| [benavlabs/FastAPI-boilerplate](https://github.com/benavlabs/FastAPI-boilerplate) | MIT | v0.19.0 2026-06-24 / 2026-09-28 | Models auto-import in `env.py`, `migrate` Docker stage | fastcrud and crudauth coupling, taskiq (dropped arq in v0.18), three-layer split, 15 settings classes |
| [alan2207/bulletproof-react](https://github.com/alan2207/bulletproof-react) | MIT | no releases / 2026-05-14 | `src/{app,components,features,lib}`, one-way imports, `queryOptions` per feature | Hand-written fetchers, axios and cookies, zustand store, MSW |

Rejected: Netflix/dispatch, archived 2025-09, schema per org. Orval (MIT,
8.41.0) generates a hook per endpoint; openapi-react-query had no 2026
release after February.

## Decision

| Area | Pick |
| --- | --- |
| Repo layout | `backend/` and `frontend/` as in the FastAPI template. One `pyproject.toml` in `backend/`, no uv workspace ([uv docs](https://docs.astral.sh/uv/concepts/projects/workspaces/)). Backend modules by domain per fastapi-best-practices and [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/). Frontend per bulletproof-react plus the [shadcn Vite guide](https://ui.shadcn.com/docs/installation/vite). |
| Settings | [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). One `Settings` class, `env_file`, `extra="ignore"`, `DATABASE_URL` as one field, `Environment` enum, a validator that rejects default secrets outside development. Shape from the FastAPI template and Polar. |
| DB session and helpers | [SQLAlchemy asyncio docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html): `async_sessionmaker(expire_on_commit=False)`, `get_session` dependency as `SessionDep`. Async with asyncpg, see [0003](../decisions/0003-async-database.md). `DeclarativeBase` with one naming dictionary in Polar's suffix form: pk `%(table_name)s_pkey`, fk `%(table_name)s_%(column_0_name)s_fkey`, uq `%(table_name)s_%(column_0_name)s_key`, ck `%(table_name)s_%(constraint_name)s_check`, ix `ix_%(column_0_N_label)s` ([mechanism](https://docs.sqlalchemy.org/en/20/core/constraints.html#configuring-constraint-naming-conventions)). One repository base class with `get`, `list`, `create`, `update`; `org_id` is a required argument on every call. |
| Migrations | [Alembic async cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic) `env.py`, `compare_type=True`, models imported in `env.py`, `file_template` date plus slug, expand and contract migrations, a single-head check in CI. One API-only Railway pre-deploy command runs `alembic upgrade head` and then the idempotent seed. The same command runs locally. |
| API client | [@hey-api/openapi-ts](https://github.com/hey-api/hey-api) (MIT, 0.99.0 2026-06-22) with the bundled fetch client and the `@tanstack/react-query` plugin. Exact version pin. Spec dumped from `app.openapi()` into `frontend/openapi.json` as in the template script. `custom_generate_unique_id` gives stable operation names. |
| CI | One `ci.yml`: a `check` job starts Compose on the runner and runs `make setup` and `make check`, a `docker` job builds `backend/Dockerfile`, and an always-run `gate` job is the only required check. No `on.paths` filters ([GitHub docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/troubleshooting-required-status-checks)). Frontend deploy with `cloudflare/wrangler-action` after the gate; Railway uses Wait for CI. Deploy details are decided in the deploy unit. |

## Conventions we take

- Dependencies as `Annotated` aliases: `SessionDep`, `CurrentUser`, `OrgContext`.
- Engine built once from settings with `pool_pre_ping=True`.
- Migrations are reversible, one head, named `YYYY-MM-DD_slug`. Every migration works with the previous code version, expand and contract style. Platform rollback never runs `downgrade`.
- Tables are plural snake_case, as `users` and `memberships` in requirements; timestamps end in `_at`.
- Frontend code calls generated `xOptions()` and `xMutation()` helpers, never raw fetch. The one exception is the presigned PUT of an image to object storage, which goes to the storage URL, not the API.
- The client sets `baseUrl` from `VITE_API_URL` and the Bearer token from one `auth` callback.
- Features never import each other; shared code lives in `components/` and `lib/`.
- First-party actions pinned to a major; third-party actions pinned to a commit SHA with the version in a comment. `uv.lock` and `package-lock.json` checked in and used with locked installs.

## Cost and revert

Five sources instead of one template, so agents read this file before each
unit. To change a pick, edit the row here; nothing else references these
sources.
