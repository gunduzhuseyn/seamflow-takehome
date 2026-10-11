# decisions

Index:

- [0001-hosting.md](0001-hosting.md) — Railway for backend parts, Cloudflare Workers static assets for the frontend
- [0002-auth.md](0002-auth.md) — sign-in always on, Clerk for identity only, tenancy in the database
- [0003-async-database.md](0003-async-database.md) — SQLAlchemy 2 async with asyncpg
- [0004-testing.md](0004-testing.md) — acceptance tests derived from requirements before code, red then green pasted, fake LLM provider, one check per package
- [0005-railway-iac.md](0005-railway-iac.md) — Railway project defined in `.railway/railway.ts`, `DATABASE_URL` built from Postgres references
- [0006-llm.md](0006-llm.md) — provider interface with a fake, tool use with `auto` and `strict`, validated tool output, one `llm_calls` row per call, cost from a price table
- [0007-background-jobs.md](0007-background-jobs.md) — one `jobs` table, arq worker on Redis, partial unique index for one active job per subject, retries counted on the row
- [0008-upload-and-processing.md](0008-upload-and-processing.md) — presigned direct upload to R2, asynchronous classification through the arq worker, polling from the browser
