# Plan: SeeFood Enterprise

Written 2026-10-11 16:30. Task received 16:00. Feature stop 18:35. Email by 18:50. Deadline 19:00.

Design: `docs/ai_docs/requirements.md`. Template: `../template` (T). Project: this folder (P).

## Approach

Revised 16:35: the template is imported whole in one unit, renamed, and stripped of the notes demo
entity and the SSE helper. Everything else (auth, tenancy, LLM slice, worker, deploy files) stays and is adapted in later units.

Sessions:

- `backend`: main checkout, backend units one at a time.
- `frontend`: git worktree `../seamflow-takehome-fe`, frontend units.
- `infra`: terminal work (R2, Railway) and the deploy files unit.
- `backend-2`: a second worktree for U6 while U5 is in review.
- Conductor: reviews, fix lists, next prompts, README.

Reviews: subagent diff review on every backend unit. Codex on U4 and U5 (storage, vision, worker, upload flow).
Frontend units get a subagent review only when the check output is doubtful.

## Units

| # | Unit | Session | Branch | Window | Depends on |
| --- | --- | --- | --- | --- | --- |
| U1 | Structure and docs | backend | main | 16:30 to 16:40 | |
| U2 | Import template: copy, rename, strip notes and SSE, generalize jobs and llm_calls | backend | chore/import-template | 16:35 to 17:00 | U1 |
| I1 | R2 bucket, token, CORS, lifecycle | infra | none | 16:35 to 16:55 | |
| U3 | Deploy: Railway project live, Workers live through CI | infra | none (config only) | 17:00 to 17:30 | U2 |
| U4 | Pipeline foundation: storage client, vision in the LLM slice, images | backend | feat/pipeline | 17:00 to 17:40 | U2 |
| F2 | App shell and Classify page with upload flow, MSW mocks | frontend | feat/classify-ui | 17:00 to 17:50 | U2 |
| U5 | Classifications API and job: uploads, create, list, get | backend | feat/classifications | 17:40 to 18:15 | U4 |
| F3 | Generated client wiring, Review queue, History, Dashboard | frontend | feat/review-history-dashboard | 17:50 to 18:35 | F2, U5 |
| U6 | Review, metrics, CSV endpoints | backend-2 | feat/review-metrics | 18:05 to 18:35 | U5 |
| U7 | Seed images, README, live demo pass, email | backend + conductor | chore/polish | 18:35 to 18:50 | all |

Merge order: U1, U2, U4, F2, U5, F3, U6, U7. U3 is configuration and has no branch.

Cut order if behind at 18:00: CSV export, then dashboard to four tiles, then batch drop.
Fallback at 17:30 if the presigned upload does not work locally in the browser: API accepts multipart and writes to storage itself.

## API contract

Every frontend unit builds against this. The backend units implement it. Paths follow the template's router conventions.

```
POST /uploads                      body {filename, content_type, size_bytes}
                                   201 {key, upload_url, expires_in}
                                   400 when content_type not in jpeg/png/webp/gif or size_bytes > 10485760
POST /classifications              body {key, filename}
                                   202 ClassificationOut (status queued)
                                   429 when the per-user rate limit is hit
GET  /classifications              query limit=50, status, review_status, verdict
                                   200 {items: ClassificationOut[], total}
GET  /classifications/{id}         200 ClassificationOut
POST /classifications/{id}/review  body {final_verdict}
                                   200 ClassificationOut
GET  /classifications/metrics      200 {total, completed, hot_dog, not_hot_dog, pending_review,
                                        reviewed, overrides, override_rate, avg_latency_ms,
                                        total_cost_usd, deduplicated}
GET  /classifications/export.csv   200 text/csv, same filters as the list

ClassificationOut {
  id, created_at, updated_at, filename, submitted_by_name,
  status: queued|processing|completed|failed,
  review_status: not_required|pending|reviewed,
  verdict: hot_dog|not_hot_dog|null, confidence: number|null, observations: string|null,
  final_verdict: hot_dog|not_hot_dog|null, reviewed_at: string|null,
  latency_ms: number|null, cost_usd: number, duplicate_of: string|null,
  thumbnail_url: string|null, error_code: string|null
}
```

## Demo script

1. Open the live URL, sign in with the seed login.
2. Drop three images at once: hot dog, burger, corn dog. Three cards appear as queued, then complete.
3. The corn dog shows "Pending review". Open Review, confirm or override it.
4. Open History, filter by verdict, export CSV.
5. Open Dashboard: totals, ratio, latency, spend, override rate.
6. Drop the same hot dog again. The card shows "Duplicate, $0.00" with no model call.

## Prompts

Common header for every session prompt:

> You work in /Users/gunduz/Desktop/projects/workbench/seamflow-takehome (P). The template is /Users/gunduz/Desktop/projects/workbench/template (T). Read P/AGENTS.md, P/docs/ai_docs/requirements.md, and the API contract in P/docs/ai_docs/plan.md first. Copy from T only the files named below. Adapt names: project `seamflow-takehome`, product "SeeFood Enterprise", repo `gunduzhuseyn/seamflow-takehome`. Do not copy notes, SSE, or anything not named. Run the done-when command and paste its real output in full. Stop, do not commit.

### U1 Structure and docs (backend session, on main)

> Create the repository structure. No application code.
> 1. `git init -b main` in P.
> 2. P/AGENTS.md: start from T/AGENTS.md. Keep the working rules. Set the project name. Add a line "Design: docs/ai_docs/requirements.md and docs/ai_docs/plan.md". Remove references to notes.
> 3. P/README.md: title "SeeFood Enterprise", one paragraph on what it does, a "Status" line, a section "AI use" that says the project was built with Claude Code and Codex as conductor, implementers, and reviewers, with the human making product and priority decisions. Keep it under 40 lines. It grows in U7.
> 4. P/.gitignore from T/.gitignore. P/.env.example from T/.env.example with the project name changed.
> 5. Folders: backend/, frontend/, docs/decisions/, backend/seed_images/ with a .gitkeep in each empty one.
> 6. P/docs/decisions/0001-upload-and-processing.md: a 25 line ADR. Context: image upload under a 3 hour window. Decision: presigned direct upload to Cloudflare R2 (RustFS locally), asynchronous classification through the arq worker, polling from the browser. Consequences: API never carries bytes, idempotent job, fallback to multipart through the API if presigning fails.
> Done when: `cd P && git status --short && find . -type f -not -path './.git/*' | sort` prints the tree and nothing else is modified.

User: commit `chore: add project structure and docs`, add the remote `git@github.com:gunduzhuseyn/seamflow-takehome.git`, push main.

### I1 Object storage (infra session, no branch)

> Set up Cloudflare R2 for project seamflow-takehome. Do not touch the repo. Write every value you create into /private/tmp/seamflow-infra-notes.md, never into the repo.
> 1. Check `npx wrangler whoami` with CLOUDFLARE_API_TOKEN from the environment or from `gh secret list -R gunduzhuseyn/seamflow-takehome` (secrets are not readable; ask me for the token value if wrangler is not authenticated).
> 2. Create bucket `seamflow-takehome` with `npx wrangler r2 bucket create seamflow-takehome`. If the token lacks R2 permission, tell me and I create the bucket in the dashboard.
> 3. CORS: write cors.json allowing origins `http://localhost:5173`, `https://seamflow-takehome.*.workers.dev` (use the exact Workers domain if known, else allow `*` for now and note it), methods PUT and GET, headers `*`, max age 3600. Apply with `npx wrangler r2 bucket cors set seamflow-takehome --file cors.json`.
> 4. Lifecycle: delete objects under prefix `incoming/` after 1 day with `npx wrangler r2 bucket lifecycle add seamflow-takehome --prefix incoming/ --expire-days 1`.
> 5. R2 S3 credentials cannot be created with the CLI. Ask me to create an R2 API token in the dashboard (R2 > Manage R2 API Tokens, Object Read and Write, bucket seamflow-takehome) and paste the Access Key ID, Secret Access Key, and the S3 endpoint `https://<account_id>.r2.cloudflarestorage.com`.
> 6. Record in the notes file: STORAGE_ENDPOINT_URL, STORAGE_ACCESS_KEY_ID, STORAGE_SECRET_ACCESS_KEY, STORAGE_BUCKET=seamflow-takehome, STORAGE_REGION=auto.
> Done when: `npx wrangler r2 bucket list` shows the bucket and `npx wrangler r2 bucket cors list seamflow-takehome` shows the rules. Paste both.

### U2 Import template (backend session, branch chore/import-template)

> Import the template whole, rename it, and strip what this product does not need.
> Before anything: `cd T && docker compose down -v` so ports are free. Then `cd P && git checkout -b chore/import-template`.
> 1. Copy: `rsync -a --exclude .git --exclude node_modules --exclude .venv --exclude '.pytest_cache' --exclude '__pycache__' --exclude dist --exclude 'docs/ai_docs/requirements.md' --exclude README.md --exclude AGENTS.md T/ P/`. Local `.env` files come along; they are gitignored and reused on purpose. Keep P's README.md, AGENTS.md, and docs/ai_docs/requirements.md. Rename P/docs/decisions/0001-upload-and-processing.md to 0008-upload-and-processing.md and add it to docs/decisions/README.md.
> 2. Rename: replace `takehome-template` with `seamflow-takehome` in README.md (template copy at T/README.md, merge its Try it and Local development sections into P/README.md under our title and AI use section), frontend/wrangler.jsonc, .railway/railway.ts (REPO `gunduzhuseyn/seamflow-takehome`, NAME `seamflow-takehome`), docs/guides/deploy.md. `grep -rn takehome-template P --exclude-dir=node_modules --exclude-dir=.git` must return nothing. Keep the worker service in railway.ts.
> 3. Strip notes: backend/app/notes/, migrations/versions/*add_notes*.py, tests that import notes (notes_support, llm_support if notes-only, acceptance/test_notes*, test_llm_summarize, test_job_* and acceptance/test_jobs if they use the note analysis job: keep the job tests by giving them a trivial test job instead), DEMO_NOTES in seed.py, the notes router and job registration in main.py and worker.py, frontend/src/features/notes, src/app/routes/notes.tsx, src/lib/sse.ts and its test, src/testing/sse-fixtures.ts, notes handlers in src/testing/handlers.ts, notes links in routes/home.tsx. Remove the SSE helpers in backend/app/llm/calls.py only if nothing else uses them; keep `run_call`'s validation logic available for the next unit.
> 4. Generalize: in jobs and llm_calls, rename `note_id` to `subject_id` (uuid, not null, no foreign key) in the models and edit the two migrations in place (fresh repo, no deployed database). Keep the unique active index on (kind, subject_id). Fix the repositories, runner, and tests that reference note_id. Keep tenancy_registry entries for jobs and llm_calls.
> 5. home.tsx becomes a placeholder "Classify" page with the product name and the signed-in user's name. index.html title "SeeFood Enterprise".
> 6. `make generate` to regenerate the client without notes operations.
> 7. Update P/docs/ai_docs/README.md and docs/guides/README.md to the new names. Do not edit requirements.md or plan.md.
> Done when: `cd P && make dev` is not required; run `docker compose up -d --wait && make check`. It must pass end to end (backend check, frontend check, railway tsc, drift). Paste the full output including the pytest summary line, the vitest summary line, and `cd backend && uv run alembic heads` showing one head.

### U3 Deploy (infra session, no branch, after U2 merged)

> Follow P/docs/guides/deploy.md steps 2 to 6 for project `seamflow-takehome`. All deploy files are already in the repo on main.
> `cd P && railway init --name seamflow-takehome`, `(cd .railway && npm ci) && railway config plan && railway config apply`. Set secrets on both api and worker with `printf '%s' '<v>' | railway variable set <NAME> --stdin --service <svc> --skip-deploys` for CLERK_SECRET_KEY, ANTHROPIC_API_KEY (copy from the takehome-template Railway project with `railway variable list` after linking it in a temp dir, or ask me), SEED_USER_EMAIL and SEED_USER_PASSWORD (ask me). Storage variables come in a later unit; do not set them now.
> Then `railway redeploy --service api --from-source --yes` and the same for worker. GitHub variables are already set; verify with `gh variable list -R gunduzhuseyn/seamflow-takehome`.
> Done when: `curl -s https://seamflow-takehome-api.up.railway.app/health` returns the health JSON. Paste it and `railway status`. CI on main deploys the frontend; paste the Workers URL from the Actions log.

### U4 Pipeline foundation (backend session, branch feat/pipeline, after U2 merged)

> Build the storage, vision, and image modules on top of the imported LLM slice and worker. Dependencies to add with uv: boto3, pillow, and boto3-stubs[s3] if pyright needs it.
> 1. app/storage/: `client.py` with a `Storage` protocol: `presign_put(key, content_type, expires_s) -> str`, `presign_get(key, expires_s) -> str`, `head(key) -> int | None` (size), `get_bytes(key) -> bytes`, `put_bytes(key, data, content_type)`, `ensure_bucket()` (create bucket and set a CORS rule allowing PUT and GET from CORS_ORIGINS; used in development only). `S3Storage` on boto3 run through `asyncio.to_thread`. `FakeStorage` in tests/fakes.py with an in-memory dict. Settings: STORAGE_ENDPOINT_URL, STORAGE_PUBLIC_ENDPOINT_URL (defaults to the endpoint; used only for presigned URLs), STORAGE_ACCESS_KEY_ID, STORAGE_SECRET_ACCESS_KEY, STORAGE_BUCKET, STORAGE_REGION. Add placeholders to the production validator. Local values for RustFS: endpoint http://localhost:9000, key and secret rustfsadmin. Call `ensure_bucket()` from a Makefile target `storage-init` that `make dev` runs after compose is up.
> 2. app/images.py: `inspect(data) -> (mime, width, height)` using Pillow and raising `InvalidImage` when not jpeg/png/webp/gif. `model_input(data) -> bytes` JPEG with the longest side 1024. `thumbnail(data) -> bytes` WebP with the longest side 320. Tests generate images with Pillow.
> 3. LLM slice (already imported): add `images: list[ImageInput]` (media_type, base64) to LLMRequest and build the content block list in anthropic_provider.py. Add `app/llm/complete.py: complete_with_tool(provider, request, output_model) -> (parsed, usage)` that consumes the stream, keeps the ToolInput and Usage, validates with the model, and retries once on validation failure. Record an LLMCall row per attempt.
> 4. app/vision/: `prompts/classify.md` (system prompt: you are a food compliance classifier, answer with the tool, verdict is binary, confidence reflects certainty, observations is one sentence under 300 chars on what is visible), `schema.py` with `VisionResult(verdict: Literal["hot_dog","not_hot_dog"], confidence: float 0..1, observations: str max 300)`, `classify.py: classify_image(session, provider, user_id, org_id, jpeg_bytes) -> (VisionResult, llm_call_id, cost_usd)`. Fixture tests/fixtures/llm/hotdog.json for the fake provider and one invalid fixture to test the retry.
> 5. Replace `check_input_limit` in limits.py with a byte cap on the model input (2 MB). Keep `enforce_rate_limit`.
> 6. One integration test marked to run only when STORAGE_ENDPOINT_URL is reachable: presign PUT, upload with httpx, head, get_bytes, presign GET, download with httpx. It runs in `make check` locally because compose is up.
> Done when: `make -C backend check` passes. Paste the full output including the pytest summary line and `alembic heads` showing one head.

### F2 App shell and Classify page (frontend session, worktree ../seamflow-takehome-fe, branch feat/classify-ui, after U2 merged)

> Create the worktree: `cd P && git worktree add ../seamflow-takehome-fe -b feat/classify-ui`. Work in its frontend folder; `npm ci` first. Build the enterprise shell and the Classify page against the API contract in plan.md, with MSW handlers. The generated client does not have these operations yet, so write `src/features/classifications/api.ts` with typed fetch wrappers using the same base URL and auth as src/lib/api-config.ts. F3 replaces them with the generated client.
> Shell: left sidebar with the product name, nav items Classify, Review, History, Dashboard (the last three route to placeholder pages), a top bar with the organization name and the Clerk UserButton. Dense, calm, grey-blue palette, shadcn components, no gradients, no emoji. Page headers with a title and one line of description.
> Classify page: a drop zone (click or drop, multiple files, accept jpeg/png/webp/gif, 10 MB cap checked client side with an inline error). For each accepted file: POST /uploads, PUT the file to upload_url with the Content-Type header, POST /classifications, then the row appears in the results. Results: a responsive card grid of ClassificationOut, newest first, from GET /classifications?limit=50 with refetchInterval 2000 while any item is queued or processing, otherwise off. Card: thumbnail (object URL of the local file until thumbnail_url arrives), filename, status chip, verdict in large text "Hot Dog" or "Not Hot Dog" with a green or slate badge, confidence bar with the percent, observations, latency and cost line, "Pending review" amber badge when review_status is pending, "Duplicate, $0.00" badge when duplicate_of is set, "Analysis failed" with the error_code when failed. Empty state with one sentence and the drop zone.
> Tests: drop two files, the three requests happen per file, cards show queued then completed after the mock flips state on the second poll.
> Done when: `npm run check` passes. Paste the full output.

### U5 Classifications API and job (backend session, branch feat/classifications, after U4 merged)

> Implement the contract's uploads and classifications endpoints and the worker job.
> Model app/classifications/models.py per requirements.md with the three indexes (jobs and llm_calls link back through their subject_id = classification id), an Alembic migration, a `ClassificationRepository(Repository)` with `list_filtered`, `find_duplicate(org_id, sha256)`. Register in tenancy_registry.
> Router: POST /uploads validates content_type and size_bytes, builds key `incoming/{org_id}/{uuid4}`, returns the presigned PUT (10 minutes). POST /classifications checks the key prefix matches the caller's org, runs enforce_rate_limit, creates the row queued, starts the job through jobs.queue.start_job, returns 202. GET list applies filters and adds `thumbnail_url` (presigned GET, 1 hour) and `submitted_by_name`. GET by id.
> Job `classify_image_job(ctx, classification_id)` in app/classifications/job.py through jobs.runner.run_job: load row; if verdict already set, return (idempotent). Set processing. `head` the key; over 10 MB sets failed with error_code too_large. `get_bytes`, `images.inspect`; InvalidImage sets failed with invalid_image. sha256; `find_duplicate` with a completed row copies verdict, confidence, observations, thumbnail_key, sets duplicate_of, cost 0, completed, and returns. Else `images.thumbnail` to `thumbs/{org_id}/{id}.webp`, `images.model_input`, `vision.classify_image`, write verdict, confidence, observations, latency_ms, cost_usd, llm_call_id, status completed, review_status pending when confidence < CLASSIFY_REVIEW_THRESHOLD (setting, default 0.85) else not_required. Provider errors raise so the jobs runner retries; after the last attempt set failed with provider_error.
> Tests with FakeStorage and FakeProvider: upload validation, key prefix check, rate limit 429, create returns 202 queued, job completes a row with the fixture result, low confidence goes pending, duplicate skips the provider and costs 0, invalid image fails with the code, tenancy test through the registry.
> Done when: `make -C backend check` passes. Paste the full output. Then start `make dev` and keep it running for the frontend session.

### F3 Wiring and pages (frontend session, branch feat/review-history-dashboard, after U5 merged)

> Run `make generate` from P against main. Replace the wrappers in src/features/classifications/api.ts with the generated client and its TanStack options. Keep the Classify page behaviour.
> Review page: table of items with review_status pending, thumbnail, verdict, confidence, observations, two buttons Confirm and Override that call POST /classifications/{id}/review with final_verdict equal or opposite. Row leaves the table on success. Empty state "Nothing waiting for review".
> History page: table of all items, filters for verdict and review_status, columns thumbnail, filename, submitted by, verdict, final verdict, confidence, status, created. "Export CSV" button that opens GET /classifications/export.csv with the current filters and the auth header through fetch and a blob download.
> Dashboard page: tiles from GET /classifications/metrics: Total classified, Hot dog ratio, Pending review, Override rate, Average latency, Total spend, Deduplicated. Two-row grid of shadcn cards.
> Also add a "Was this correct?" row on each completed Classify card with two small buttons calling the review endpoint.
> Tests with MSW: review removes the row, history filter changes the query, dashboard renders tiles.
> Done when: `npm run check` passes and `make drift` from P passes. Paste both.

### U6 Review, metrics, CSV (backend-2 session, worktree ../seamflow-takehome-be2, branch feat/review-metrics, after U5 merged)

> Add three endpoints to app/classifications/router.py per the contract. Review: only completed rows; sets final_verdict, reviewed_by, reviewed_at, review_status reviewed; 409 otherwise. Metrics: one aggregate query with count, sum(case), avg, and override count as final_verdict is not null and differs from verdict. CSV: StreamingResponse with the csv module, same filters as list, columns id, created_at, filename, submitted_by, verdict, final_verdict, confidence, status, review_status, latency_ms, cost_usd, duplicate_of.
> Tests: review happy path and 409, metrics numbers on five seeded rows, CSV header and row count, tenancy for all three.
> Done when: `make -C backend check` passes. Paste the full output.

### U7 Polish (backend session, branch chore/polish)

> 1. seed.py: for each file in backend/seed_images/, compute sha256; skip when a classification with that hash exists in the demo org; else put_bytes to `incoming/{org_id}/{uuid}`, create the row queued, start the job. Seed stays idempotent.
> 2. README: sections What it is, Live demo (URL, how to sign in is in the email), Architecture (ten lines and an ASCII diagram browser to R2 to API to Redis to worker to Claude to Postgres), Product decisions (review queue, dedupe, confidence threshold, batch), Tradeoffs and next steps (from the cut list), Local development (`make dev`, `make check`), Deploy (link to docs/guides/deploy.md), AI use.
> Done when: `make check` passes and `make dev` seeds the six images, visible in the Classify page. Paste the check output and the seed log lines.
