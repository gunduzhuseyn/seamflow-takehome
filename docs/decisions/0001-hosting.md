# Hosting

## Context

The app has an API, a worker, Postgres, Redis, a file bucket, and a
static frontend. It must deploy from a push to main, roll back, and
stay under a spend cap.

## Decision

API and worker run as Docker containers on Railway, with Railway
Postgres, Redis, and bucket in one project. The frontend deploys to
Cloudflare Workers as static assets, with no Worker script. Deploys wait
for CI. Migrations run pre-deploy and work with the previous code
version.

The deploy unit changed the frontend host from Cloudflare Pages to
Workers on 2026-10-11.

## Why

- One vendor and one bill for every backend part.
- Railway's hard spend limit takes the app offline instead of charging.
- The frontend on Workers gets an independent deploy and a CDN.
- Cloudflare directs new projects to Workers. Wrangler sends a new Pages
  project that an agent creates to Workers. Each copy of the template is
  a new project, often made by an agent.
- The first `wrangler deploy` creates the Worker, so no console step
  creates it. `wrangler rollback` rolls back from the CLI.
- Static asset requests are free and have no limit.

## Cost

Two origins, so CORS and an API base URL per environment. No CDN in
front of the API. A code rollback does not roll back the schema.
`frontend/wrangler.jsonc` must turn on the single-page application
fallback. The URL includes the account's workers.dev subdomain.

## How to revert

The Dockerfiles build on any container host. Move the services, change
the database, Redis, and bucket settings, and update CI. To serve the
frontend from the API instead, mount the build in FastAPI. To use Pages,
delete `frontend/wrangler.jsonc` and deploy with `wrangler pages deploy`.
A human creates the Pages project, or the agent passes `--force`.
