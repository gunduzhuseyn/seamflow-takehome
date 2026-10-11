# SeeFood Enterprise

SeeFood Enterprise classifies images as "Hot Dog" or "Not Hot Dog" for teams.
A user signs in, drops one or more images, and reads a verdict with a confidence score.
The browser uploads each image straight to object storage. A worker runs the vision
model and writes the result. Verdicts below the confidence threshold go to a review
queue, where a team member confirms or overrides them. History supports filters and
CSV export. The dashboard shows totals, hot dog ratio, latency, spend, and override rate.

Status: template imported. Sign-in, tenancy, jobs, and the LLM slice work. Classification comes in later units.

## AI use

This project was built with Claude Code and Codex. They acted as conductor,
implementers, and reviewers. The human made the product and priority decisions.

## Try it

- Open <https://seamflow-takehome.gunduzhuseyn.workers.dev>.
- A seed login exists with the `admin` role in the `Demo` organization.
  The owner shares it with you directly. It is never in the repository.
- When Clerk asks the seed login for an email code, enter `424242`.
- Sign-up also works. A new account gets its own empty organization.
- To run it on your machine, see [Local development](#local-development).

## Local development

### Prerequisites

| Tool | Version | Source |
| --- | --- | --- |
| Docker with Compose v2 | Docker 29, Compose 5 | tested versions |
| uv | 0.13 | tested version |
| Node | 24 | `frontend/.nvmrc` |
| Python | 3.14 | `backend/.python-version`; uv installs it when missing |

### Run locally

Sign-in is always on, so you need a Clerk development instance. Ask the
owner for the shared one, or create your own at
<https://dashboard.clerk.com> with email and password sign-in only.
**Configure > API keys** shows its publishable key, JWT public key, and
secret key.

`make setup` creates `.env` and `frontend/.env` from the examples. Before
the first run, set these values in `.env`. The seed refuses the example
values.

- `CLERK_SECRET_KEY`: the secret key.
- Your own instance only: `CLERK_PUBLISHABLE_KEY` and `CLERK_JWT_KEY` in
  `.env`, and `VITE_CLERK_PUBLISHABLE_KEY` in `frontend/.env`. Write the
  PEM on one line, with each newline as `\n`. The shared instance's keys
  are the defaults.
- `SEED_USER_EMAIL`: a `+clerk_test` address, for example
  `you+clerk_test@example.com`.
- `SEED_USER_PASSWORD`: a long password.
- `ANTHROPIC_API_KEY`: a key from an Anthropic Console workspace, for the
  vision model. With `LLM_PROVIDER=fake`, the app replays test fixtures
  instead, and the key keeps its example value.

```sh
make dev
```

The command creates `.env` and `frontend/.env` from the examples, installs
both packages, starts Compose, runs migrations, runs the seed, and starts
three processes: the API, the frontend, and the arq worker. Ctrl-C stops
all three.

The seed creates the `Demo` organization and the seed user from
`SEED_USER_EMAIL` and `SEED_USER_PASSWORD`. Sign in with those values. A
new user gets a personal organization on first sign-in.

Clerk asks for an email code when a user signs in on a new device. The
seed email has the `+clerk_test` sub-address, so Clerk sends no email.
Enter `424242` as the code. This works on development instances only.

- Frontend: <http://localhost:5173>
- API health: <http://localhost:8000/health>

`make down` stops Compose.

### Checks

```sh
make check
```

Compose must be up. The command runs the backend check (ruff, pyright,
alembic check, pytest), the frontend check (eslint, prettier, tsc, vitest,
vite build), and the drift check. The drift check regenerates the OpenAPI
document and the client into a temporary directory and compares them with
the committed files.

CI runs the same commands on every push to `main` and on every pull
request. See the runs in the repository's Actions tab.

### Regenerate the API client

```sh
make generate
```

Run it after each API change and commit `frontend/openapi.json` and
`frontend/src/lib/api/`.

## Deploy

A push to `main` deploys after CI passes. Railway runs the API, the arq
worker, Postgres, and Redis. A Cloudflare Worker serves the frontend.
Setup, rollback, spend limits, and teardown are in [docs/guides/deploy.md](docs/guides/deploy.md).

- Frontend: <https://seamflow-takehome.gunduzhuseyn.workers.dev>
- API health: <https://seamflow-takehome-api.up.railway.app/health>

## Layout

- `backend/` FastAPI app, Alembic migrations, tests.
- `frontend/` React app with the generated client in `src/lib/api/`.
- `compose/` files mounted into Compose services.
- `docs/` requirements, plan, decisions, and guides.
