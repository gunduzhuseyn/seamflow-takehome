# Deploy

The API, the worker, Postgres, and Redis run in one Railway project. The
frontend is a Cloudflare Worker that serves static assets. A push to
`main` runs CI. When CI passes, the `deploy-frontend` job deploys the
Worker, and Railway deploys the API and the worker.

## Naming convention

Each copy of the template has its own repository, Railway project, and
Worker. Only the accounts are shared. All three use the repository name.
In this file, `<name>` is the repository name, `<owner>` is the GitHub
account, and `<sub>` is the account's workers.dev subdomain.

| Item | Pattern | This repository |
| --- | --- | --- |
| Railway project | `<name>` | `seamflow-takehome` |
| API URL | `https://<name>-api.up.railway.app` | `https://seamflow-takehome-api.up.railway.app` |
| Worker | `<name>` | `seamflow-takehome` |
| Frontend URL | `https://<name>.<sub>.workers.dev` | `https://seamflow-takehome.gunduzhuseyn.workers.dev` |

## What a new copy changes

- `.railway/railway.ts`: `REPO` and `NAME`. `CORS_ORIGINS` and the API
  domain follow `NAME`. On another Cloudflare account, change
  `WORKERS_SUBDOMAIN` too.
- `frontend/wrangler.jsonc`: `name`.
- Railway variables on `api`, step 4: `CLERK_SECRET_KEY` is the same for
  every copy. `SEED_USER_EMAIL`, `SEED_USER_PASSWORD`, and
  `ANTHROPIC_API_KEY` are new per copy.
- GitHub secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. The
  account ID is the same for every copy. Make one token per copy.
- GitHub repository variable `VITE_API_URL`: the API URL.
- GitHub repository variable `VITE_CLERK_PUBLISHABLE_KEY`: the publishable
  key of the shared Clerk development instance. It is the same for every
  copy and is the default in `frontend/.env.example`.
- The README URLs.

The Clerk publishable key and JWT public key are committed defaults in
`backend/app/core/config.py` and `frontend/.env.example`. A copy on
another Clerk instance changes both files.

## Tools

| Tool | Version tested | Install |
| --- | --- | --- |
| Railway CLI | 5.64.2 | `brew install railway` |
| wrangler | 4.149.0 | none, run `npx wrangler@4.149.0` in `frontend/` |
| GitHub CLI | 2.x | `brew install gh` |

## One-time account setup

Do these once per account, not once per copy.

1. Railway: the workspace must be on the Hobby plan or higher. The Free
   plan cannot set a hard limit. Open
   <https://railway.com/workspace/plans>.
2. GitHub: install the Railway App on your account. Open
   <https://github.com/apps/railway-app/installations/new>, select
   **Only select repositories**, and add the copy's repository. For a
   later copy, add its repository under
   <https://github.com/settings/installations>, **Railway App >
   Configure**. Signing in to Railway with GitHub does not install it.
3. Cloudflare: register a workers.dev subdomain. Open **Workers & Pages**.
   The subdomain shows in the account details panel.
4. Clerk: one development instance serves every copy. Create it once at
   <https://dashboard.clerk.com>. Sign-in options: email and password
   only. **Configure > API keys** shows the publishable key, the secret
   key, and the JWT public key.
5. Anthropic: one Console organization with credits, at
   <https://console.anthropic.com>. Each copy gets its own workspace and
   key in step 1.
6. Run `railway login` and `npx wrangler@4.149.0 login`.

Check: `railway whoami` and `npx wrangler@4.149.0 whoami` show your
account. `wrangler whoami` also shows the account ID.

## Steps for each copy

Do the steps in order. Each step has a check. Do not continue until the
check passes.

### 1. Spend limits

Set or confirm the limits before the first deploy. The Railway limit is
for the whole workspace, so it covers every copy.

```sh
railway usage limit set --target workspace --soft 24 --hard 48
```

Check: `railway usage limit status` shows both values.

Anthropic limits are per Console workspace, so each copy gets one:

1. Open **Settings > Workspaces > Create Workspace**. Name: `<name>`.
2. Open the workspace, then **Limits**. Monthly spend limit: `20`. Alert
   threshold: `10`. See [Spend limits](#spend-limits) for the numbers.
3. Open **API Keys > Create Key** in that workspace. Name: `<name>-api`.
   Copy the key. It is shown once. It goes into `.env` locally and into
   the Railway variable in step 4.

Check: the workspace page shows both limits, and the key list shows one
key.

### 2. Railway project

Run in the repository root:

```sh
railway init --name <name>
```

Check: `railway status` shows project `<name>`.

### 3. Railway services

```sh
(cd .railway && npm ci)
railway config plan     # creates Postgres, Redis, api, worker. Deletes nothing.
railway config apply
```

The file sets these values on `api`:

| Setting | Value |
| --- | --- |
| Source | GitHub `<owner>/<name>`, branch `main`, root directory `/backend` |
| Watch paths | `/backend/**`, `/.railway/**`: a push that changes neither path does not deploy `api` |
| Wait for CI | on |
| Build | `backend/Dockerfile`, found by Railway |
| Pre-deploy command | `sh -c 'alembic upgrade head && python -m app.seed'` |
| Healthcheck | `/health`, timeout 60 s |
| Restart policy | on failure, 3 retries |
| Domain | `<name>-api.up.railway.app`, port 8000 |
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` |
| `DATABASE_URL` | `postgresql+asyncpg://` built from the `Postgres` reference variables |
| `REDIS_URL` | reference to `Redis.REDIS_URL` |
| `CORS_ORIGINS` | the frontend URL |

Logs from `api` are JSON, one object per line. Each request writes one line with `request_id`, `method`, `path`, `status`, and `duration_ms`.
To find the lines of one request, run `railway logs --service api --lines 200 --filter '"<request-id>"'`. The CLI filters deploy logs by text and `@level` only. Its `--request-id` flag reads Railway's HTTP logs, which use a different id.

The file sets these values on `worker`:

| Setting | Value |
| --- | --- |
| Source, watch paths, Wait for CI, build | the same as `api` |
| Start command | `arq app.worker.WorkerSettings` |
| Pre-deploy command, healthcheck, domain | none. `api` runs the migrations; nothing connects to the worker |
| Restart policy | on failure, 3 retries |
| Variables | references to the `api` variables, so each secret is set once in step 4 |

Logs from `worker` are JSON lines too. Each job writes `job started`, then
`job succeeded`, `job retry`, or `job failed`, with `job_id`, `kind`,
`status`, `attempts`, and the `request_id` of the request that queued it.
`railway logs --service worker --lines 200 --filter '"<request-id>"'`
shows the job lines of one request. `railway logs --service worker
--filter '"<job-id>"'` shows one job. arq writes its own lines as well,
with the job id and the function name.

The first `api` and `worker` deploys start at once and build the current
`main`. They fail until step 4 sets the secrets.

Check: `railway config plan` shows two changes only, one per service:
`deploy.restartPolicyType (null → "ON_FAILURE")` for `api` and for
`worker`. Railway stores the default as null, so these lines stay. Other
changes mean the apply failed. A first apply can leave
`worker source.checkSuites (null → true)`; a second apply sets it.

### 4. Railway secrets

Set the four secrets on `api`. The API, the seed, and the worker do not
start without them. `.railway/railway.ts` declares them with `preserve()`,
so `railway config apply` keeps their values. Without `preserve()`, apply
deletes every variable that the file omits. The worker reads them through
references, so it needs no values of its own.

```sh
printf '%s' '<value>' | railway variable set <NAME> --stdin --service api --skip-deploys
```

| Variable | Value |
| --- | --- |
| `CLERK_SECRET_KEY` | secret key of the shared Clerk development instance, **Configure > API keys** |
| `SEED_USER_EMAIL` | sign-in email of the seed user. Use a `+clerk_test` address, for example `reviewer+clerk_test@example.com`. The email code is then always `424242` |
| `SEED_USER_PASSWORD` | password of the seed user. Clerk keeps the first password of an email, so a later change has no effect |
| `ANTHROPIC_API_KEY` | the key of this copy's Console workspace, step 1 |

In production, the API refuses to start when a variable still has its
`.env.example` value. The error names the variable. The seed refuses the
example login values in every environment.

Share the seed login with the people who test the copy. Never put it in
the repository.

Then deploy `main` again:

```sh
railway redeploy --service api --from-source --yes
railway redeploy --service worker --from-source --yes
```

Check: `railway deployment list --service api` and `--service worker`
show a new `SUCCESS` deployment each. `railway logs --service api` shows
`Seeded org 'demo' and user <email>`. `railway logs --service worker`
shows `worker started`.

### 5. Cloudflare API token

1. Open **My Profile > API Tokens > Create Token > Create Custom Token**.
2. Name: `<name>-deploy`.
3. Permissions: **Account > Workers Scripts > Edit**. Nothing else.
4. Account resources: **Include > your account**.
5. Copy the token. Cloudflare shows it once.

Check: `curl -s -H "Authorization: Bearer <token>" https://api.cloudflare.com/client/v4/user/tokens/verify`
returns `"status": "active"`.

### 6. GitHub secrets and variables

```sh
gh secret set CLOUDFLARE_API_TOKEN      # paste the token
gh secret set CLOUDFLARE_ACCOUNT_ID     # paste the account ID
gh variable set VITE_API_URL --body https://<name>-api.up.railway.app
gh variable set VITE_CLERK_PUBLISHABLE_KEY --body <publishable key>
```

Check: `gh secret list` shows both secrets. `gh variable list` shows
`VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY`.

### 7. First deploy

Merge a pull request to `main`. The first `wrangler deploy` creates the
Worker.

Check:

- `gh run list --branch main --limit 1` shows success.
- `railway deployment list --service api` and `--service worker` show a
  new `SUCCESS` deployment each.
- `curl -s https://<name>-api.up.railway.app/health` returns
  `{"status":"ok","db":"ok","redis":"ok"}`.
- `curl -s https://<name>-api.up.railway.app/me` returns
  `{"detail":"Not authenticated"}`.
- The frontend URL shows the sign-in form. Sign in with the seed login and
  the code `424242`. The page shows role `admin` in the `Demo`
  organization and three `ok` health values.

## Roll back

A rollback never runs a migration `downgrade`. Each migration works with
the previous code version.

Railway:

1. Run `railway deployment list --service api`. Copy the ID of an earlier
   deployment that ran successfully. Its status is now `REMOVED`.
2. Run the rollback. The CLI has no rollback command, so call the API:

   ```sh
   railway api 'mutation { deploymentRollback(id: "<deployment-id>") }'
   ```

   The result is `{"data":{"deploymentRollback":true}}`. In the
   dashboard, the same action is **api > Deployments > ⋮ > Rollback**.
3. Check: `railway deployment list --service api` shows a new `SUCCESS`
   deployment. `railway deployment list --service api --json` shows
   `"reason": "rollback"` in its `meta`. `/health` returns ok.

Railway keeps images of removed deployments for 72 hours on Hobby. After
that, revert the commit and push.

Frontend, in `frontend/`:

1. Run `npx wrangler@4.149.0 deployments list` and pick a version ID.
2. Run `npx wrangler@4.149.0 rollback <version-id>`. Or use **Workers &
   Pages > `<name>` > Deployments > Rollback**.
3. Check: `npx wrangler@4.149.0 deployments list` shows the version at
   100%, and the frontend URL loads.

Workers rolls back to one of the last 100 versions only. A rollback on
one side does not roll back the other side. API changes in one release
are additive, so an old frontend works with a new API.

Railway waits for all of CI, so a new frontend runs against the previous
API for a few minutes.

## Spend limits

Rule from requirements: hard limit at four times expected monthly cost,
alert at two times. The Railway limit covers the whole workspace. Plan for
three copies that run at the same time.

| Value | Amount |
| --- | --- |
| One idle project, measured | 3.77 USD per month, rounded up to 4 |
| Expected, three projects | 12 USD per month |
| Alert, two times expected | 24 USD |
| Hard limit, four times expected | 48 USD |

Measured on 2026-10-11 with `railway metrics --all --since 5m --cpu
--memory` and Railway prices of 20 USD per vCPU-month and 10 USD per
GB-month of memory:

| Service | vCPU | Memory | USD per month |
| --- | --- | --- | --- |
| api | 0.070 | 165 MB | 3.02 |
| Postgres | 0.001 | 54 MB | 0.55 |
| Redis | 0.003 | 13 MB | 0.20 |

Volumes held less than 1 MB, so their cost is near zero. The worker
service is not in this table: measure it after its first deploy. The
bucket adds cost too. Measure again when its unit exists.
`railway usage projects --project <name>` shows the cost so far.

At the hard limit, Railway stops every service in the workspace. Raise the
limit to start them again. Workers static asset requests are free and
have no limit.

Before you hand the app over, check that current usage plus the next 14
days stays under the hard limit: `railway usage`.

Anthropic, per copy. One image classification costs about 0.005 USD
with `claude-sonnet-5-5`: about 1,600 input tokens for a 1024 px image
and the prompt, and under 100 output tokens, at 2 and 10 USD per million.
This is an estimate from the token pricing, not a measurement. Measure it
after the first live calls and update this table. Expected use is up to a
thousand classifications a month.

| Value | Amount |
| --- | --- |
| Expected | 5 USD per month |
| Alert, two times expected | 10 USD |
| Hard limit, four times expected | 20 USD |

At the hard limit, the API returns an error for that workspace until the
month rolls over. Raise the limit in the Console to continue. The
workspace page shows the spend so far.

## Known issues

- Railway's builder supports only `RUN --mount=type=cache`, and only
  with a service-specific `id`. `backend/Dockerfile` uses no `RUN --mount`
  for this reason.
- Railway ignores a builder setting from `.railway/railway.ts`. It builds
  `backend/Dockerfile` because the file exists.
- When an agent runs `wrangler pages project create`, wrangler creates a
  Worker instead. This repository uses Workers for this reason. See
  `docs/decisions/0001-hosting.md`.

## Teardown

Remember: do this when a copy is retired.
Each idle copy uses a share of the workspace limit.

1. Railway: run `railway delete --project <name>`, or open the project
   and use **Settings > Danger > Delete project**.
2. Cloudflare, in `frontend/`: run `npx wrangler@4.149.0 delete`.
3. Cloudflare: delete the token `<name>-deploy`.
4. GitHub: remove the repository from the Railway App, if you selected
   repositories.
5. Anthropic: archive the `<name>` workspace in **Settings > Workspaces**.
   Its key stops working.
6. Check: `railway list` no longer shows `<name>`. In **Workers & Pages**,
   `<name>` is gone.
