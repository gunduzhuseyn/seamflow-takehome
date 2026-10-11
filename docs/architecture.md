# Architecture

SeeFood Enterprise, 2026-10-11. See `docs/decisions/` for the reasons behind each choice.

## Components

```
                 ┌──────────────────────────────────────────────────────────┐
                 │  Browser (React, Vite, Clerk, TanStack Query)            │
                 │  Cloudflare Workers static assets                        │
                 └───────┬──────────────────────────────┬───────────────────┘
          presigned PUT  │                              │  JSON + Clerk JWT
                         ▼                              ▼
          ┌───────────────────────┐          ┌─────────────────────────────┐
          │  Cloudflare R2        │          │  API: FastAPI on Railway    │
          │  incoming/{org}/{id}  │◀── get ──│  presign, create, list,     │
          │  thumbs/{org}/{id}    │◀── put ──│  review, metrics, export    │
          └───────────────────────┘    │     └──────┬──────────────┬───────┘
                         ▲             │            │ enqueue      │ read/write
                         │             │            ▼              ▼
                         │   ┌─────────┴─────────┐ ┌──────┐   ┌──────────────┐
                         └───│ Worker: arq       │◀│Redis │   │ Postgres     │
                             │ validate, hash,   │ └──────┘   │ users, orgs, │
                             │ dedupe, resize,   │────────────▶│ memberships, │
                             │ call Claude       │            │ classific.,  │
                             └─────────┬─────────┘            │ jobs,        │
                                       │ forced tool call     │ llm_calls    │
                                       ▼                      └──────────────┘
                             ┌───────────────────┐
                             │ Claude (vision)   │
                             └───────────────────┘
```

| Component | Role                                                             | Where                                                   |
| --------- | ---------------------------------------------------------------- | ------------------------------------------------------- |
| Frontend  | Classify, Review, History, Dashboard pages; generated API client | `frontend/`                                             |
| API       | Auth, tenancy, presigned uploads, classification endpoints       | `backend/app/`                                          |
| Worker    | `classify_image` job, idempotent, retried by the jobs runner     | `backend/app/classifications/job.py`                    |
| Storage   | S3 client, RustFS in development, R2 in production               | `backend/app/storage/`                                  |
| Vision    | Prompt template, tool schema, per-attempt call records           | `backend/app/vision/`, `backend/app/llm/`               |
| Database  | Alembic migrations, organization-scoped repositories             | `backend/migrations/`, `backend/app/core/repository.py` |

## Classify sequence

```
Browser          API                R2            Redis        Worker          Claude      Postgres
  │ POST /uploads │                  │              │             │               │            │
  │──────────────▶│ validate type/size, key = incoming/{org}/{uuid}              │            │
  │◀──────────────│ 201 {key, upload_url}                                        │            │
  │ PUT bytes ───────────────────────▶│              │             │               │            │
  │ POST /classifications {key, question_label}     │             │               │            │
  │──────────────▶│ rate limit, row queued ────────────────────────────────────────────────────▶│
  │◀──────────────│ 202           enqueue ──────────▶│ job ───────▶│               │            │
  │ GET /classifications every 2 s while in flight  │             │ head, get ◀───│            │
  │               │                  │◀─────────────────────────────│ inspect, sha256, dedupe?  │
  │               │                  │◀── put thumbnail ────────────│               │            │
  │               │                  │              │             │ image + tool ─▶│            │
  │               │                  │              │             │◀─ verdict ─────│            │
  │               │                  │              │             │ write result, cost ────────▶│
  │◀──────────────│ list with verdict, confidence, presigned thumbnail_url                      │
```

## Data model

- `classifications`: organization_id, submitted_by, filename, original_key, image_sha256,
  thumbnail_key, question_label, status (queued, processing, completed, failed),
  review_status (not_required, pending, reviewed), verdict (match, no_match), confidence,
  observations, final_verdict, reviewed_by, reviewed_at, latency_ms, cost_usd, llm_call_id,
  duplicate_of, error_code.
- Indexes: (organization_id, created_at desc), (organization_id, image_sha256, question_label),
  (organization_id, review_status).
- `jobs` and `llm_calls` link to a classification through `subject_id`.

## Failure handling

| Case                                       | Result                                                         |
| ------------------------------------------ | -------------------------------------------------------------- |
| Wrong type or size declared                | 400 from `POST /uploads`, nothing stored                       |
| Object missing, too large, or not an image | Row failed with `missing_object`, `too_large`, `invalid_image` |
| Provider error or invalid tool output      | Retried twice, then failed with `provider_error`               |
| Rate limit                                 | 429 from `POST /classifications`                               |
| Low confidence                             | Verdict shown, row pending in Review                           |

## What to improve

Agreed on 2026-10-11 at the end of the window, in priority order.

1. Retry button for failed cards, backed by a `POST /classifications/{id}/retry` route.
2. Collections: save a History filter as a named dataset, rerun it with a new question
   label or model, and compare the verdicts across runs.
3. Organization settings page: default question label, confidence threshold, model choice.
4. Plans: a free tier and a premium tier that set the batch size, file size limit, and
   monthly classification quota per organization.
5. Responsive sidebar and tables under 768 px.
