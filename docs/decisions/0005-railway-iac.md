# Railway configuration as code

## Context

The API service needs a Dockerfile build, a pre-deploy migration, a
healthcheck, a restart policy, Wait for CI, and variables. Railway
deprecated `railway.toml` and `railway.json` in August 2026. New services
ignore them. Existing files stop being read on 2026-12-01.

## Decision

`.railway/railway.ts` defines the whole Railway project: Postgres, Redis,
and the API service. The `railway` npm package in `.railway/` supplies the
helpers, pinned exactly. The owner applies the file with
`railway config plan` and `railway config apply`. Railway does not read
the file during a deploy.

`DATABASE_URL` is built in the file from the Postgres reference
variables, with the `postgresql+asyncpg://` scheme. Settings and Alembic
read it as is. No code normalises the scheme.

## Why

- It is the mechanism that Railway documents now. A `railway.toml` has no
  effect on a new service.
- The settings are in git, and a plan shows drift before an apply.
- Building the URL in Railway needs no code. `migrations/env.py` reads
  `DATABASE_URL` from the environment, so a Settings validator alone does
  not cover migrations.

## Cost

One more npm package and one CLI on the owner's machine. Railway deletes
each resource that the file omits, so the worker and the bucket go into
this file. A change made in the dashboard is lost at the next apply.

## How to revert

Delete `.railway/`. Set the same values in the service settings. The
values are in `docs/guides/deploy.md`.
