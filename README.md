# SeeFood Enterprise

SeeFood Enterprise is a visual yes/no check platform for teams. The default check
is "Is this a hot dog?". A team member changes the question label to run any other
check. Each image gets a definitive verdict with a confidence score, and uncertain
results wait in a review queue.

Live app: <https://seamflow-takehome.gunduzhuseyn.workers.dev>. Built in three hours
as a timed take-home. The sign-in details are in the submission email.

## AI use

This project was built with Claude Code and Codex. They acted as conductor,
implementers, and reviewers. The human made the product and priority decisions.
Requirements, plan, and session prompts are in `docs/ai_docs/`.

## Demo script

1. Sign in with the seeded reviewer account.
2. Keep the question "hot dog", or type another label.
3. Drop several images at once. Each card goes from queued to a verdict.
4. Drop the same image again. The card shows "Duplicate, $0.00" with no model call.
5. Open Review. Confirm or override a result that fell under the confidence threshold.
6. Open History, filter by question, status, or verdict, export CSV.
7. Open Dashboard: totals, match ratio, latency, spend, override rate.

## Features

- Question label per request, default hot dog, validated and treated as data in the prompt.
- Batch drop with a live status per card: queued, processing, verdict, failed.
- Verdict, confidence bar, and one sentence on what the model saw.
- Confidence threshold (0.85) routes uncertain results to a shared review queue.
- "Was this correct?" on any card records an override.
- Deduplication by image hash and question label, at zero cost.
- History with status, verdict, review, and question filters, pagination, CSV export.
- Dashboard with totals, match ratio, pending review, override rate, latency, spend.
- Organization tenancy, per-user rate limit, cost and tokens recorded per model call.

## Architecture

```
Browser ──presigned PUT──▶ Cloudflare R2 (originals, thumbnails)
   │                            ▲        │
   │ JSON + Clerk JWT           │ put    │ get
   ▼                            │        ▼
FastAPI (Railway) ──enqueue──▶ Redis ──▶ arq worker ──▶ Claude (forced tool)
   │                                      │
   └──────────────▶ Postgres ◀────────────┘
       users, organizations, memberships, classifications, jobs, llm_calls
```

Classify flow:

1. The browser asks `POST /uploads` for a presigned URL. The API validates type and size and returns a server-generated key.
2. The browser PUTs the file to R2. The API never carries image bytes.
3. `POST /classifications` creates a queued row and enqueues a job. It returns 202.
4. The worker checks the object size, downloads it, and verifies the format by magic bytes.
5. It hashes the bytes. A match on hash and label in the organization copies the earlier verdict at zero cost.
6. It writes a 320 px thumbnail to R2 and sends a 1024 px copy to Claude with a forced tool schema.
7. It stores verdict, confidence, observations, latency, cost, and the model call record.
8. The browser polls the list every two seconds while any row is in flight.

See [docs/architecture.md](docs/architecture.md) for the component and sequence diagrams.

## Key decisions

- Direct upload to object storage keeps upload bandwidth and memory off the API.
- An asynchronous worker isolates the model call, gives retries, and scales by replicas.
- Polling over SSE: simpler, and good enough at this scale.
- Forced tool output: the model can only answer with a verdict, a confidence, and one sentence.
- The dedupe key includes the question label, so a new question reruns the model.
- Thumbnails are presigned URLs, so Postgres stays small.
- A tested template provided auth, tenancy, migrations, the LLM slice, the worker, CI, and deploy.
  See `docs/decisions/` for the hosting, auth, database, testing, LLM, jobs, and upload decisions.

## Security notes

- The question label is user input. It must match a strict pattern, may not contain
  instruction-like words, and goes into the user turn as data, never into the system prompt.
- The client declares type and size, but the worker re-derives both from the bytes.
- Object keys are server generated and prefixed by organization. Every query is organization scoped.
- Per-user rate limit on classification requests. Production refuses placeholder secrets.
- A bucket lifecycle rule deletes originals after one day.

## Known limitations and next steps

- Clerk runs on a development instance.
- No retry button on failed cards. The job retries provider errors twice on its own.
- No organization settings page; the question label is per request and remembered in the browser.
- No rerun of past images with a new question.
- The sidebar is not responsive under 768 px.
- Presigned thumbnail URLs expire after one hour on a page left open without activity.
- CSV export loads matching rows in memory before streaming.
- `LLM_RATE_LIMIT_PER_MINUTE` is set on Railway by hand and not preserved in `railway.ts`.

## Local development

### Prerequisites

| Tool                   | Version              | Source                                                 |
| ---------------------- | -------------------- | ------------------------------------------------------ |
| Docker with Compose v2 | Docker 29, Compose 5 | tested versions                                        |
| uv                     | 0.13                 | tested version                                         |
| Node                   | 24                   | `frontend/.nvmrc`                                      |
| Python                 | 3.14                 | `backend/.python-version`; uv installs it when missing |

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
