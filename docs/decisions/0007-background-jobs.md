# Background jobs

## Context

Long work runs outside the request. The requirements ask for retries with
a bound, idempotent effects, one active job per record, a status the UI
can poll, and a request id that follows the job into the logs. The queue
is arq on Redis, decided in requirements. The job state lives in Postgres,
so the API reads it with the same session and org filter as every other
table.

## Decision

- **One `jobs` table** for every kind of job. Columns: `kind`, `subject_id`,
  `idempotency_key`, `status`, `attempts`, `max_attempts`, `result`,
  `error`, `request_id`, and three timestamps. `kind` is also the arq
  function name, so the API enqueues by it. `subject_id` is the id of
  the row the job works on, with no foreign key, so a new kind names its
  own table without a migration.
- **One active job per subject** is a partial unique index on
  `(kind, subject_id)` where the status is `queued` or `running`. The
  database enforces it, so two requests at the same time cannot both
  insert. The route checks first for a plain 409, and treats the
  integrity error as the same 409. A check alone has a race window;
  decisions/0004 skips the race test because the index is the guard.
- **Idempotency key** is `{kind}:{subject_id}:{job id}`. It is the arq job
  id, so arq ignores a second enqueue of the same row. The row's own
  status makes the effect idempotent: the worker returns without a change
  when the row is already `succeeded` or `failed`.
- **Claim.** The runner moves the row from `queued` to `running` with one
  conditional `UPDATE ... RETURNING`, which also increments `attempts`.
  No row means the job is finished or another worker holds it, and the
  runner returns. Every later write is a statement, after a rollback on
  the error path, so a database error inside the work still gets stored.
- **Retries** count on the row. On an exception, the runner stores the
  error, sets `queued`, and raises arq `Retry` with a delay of `attempts`
  seconds. At `max_attempts` it sets `failed` and re-raises, so the
  worker log has the traceback. arq's `max_tries` equals
  `WORKER_MAX_ATTEMPTS`, so arq never runs a try the row does not expect.
- **Order of writes.** The route commits the `queued` row, then enqueues.
  The worker always finds the row. An enqueue error marks the row
  `failed` with the reason.
- **Context.** The worker startup builds one engine, one sessionmaker, and
  the settings into the arq context. A job function takes that context
  and the job id, and `app/jobs/runner.py` runs the lifecycle. The runner
  sets the request id contextvar from the row, so worker log lines carry
  the id of the request that started the job.
- **Queue name** is a setting. Tests use one name per run on the real
  Redis from Compose, so parallel runs do not share a queue. fakeredis is
  not used.
- **Dependency.** arq 0.28.0 pins `redis<6` and is in maintenance mode.
  `[tool.uv] override-dependencies` keeps the pinned redis. The
  burst-worker test runs the real pair.
- **Railway** runs the worker as a second service on the same image, with
  the start command `arq app.worker.WorkerSettings`, no domain, no
  healthcheck, and variables that reference `api`.

## Consequences

- A new job kind is one function, one `kind` string, and one route that
  calls `start_job`. The table, the runner, and the UI polling stay.
- A job that arq cancels, at `job_timeout` or at a worker shutdown, ends
  `failed` with the error `cancelled`. arq does not run a job again after
  a timeout, so the row never waits on a run that does not come. The
  Retry button starts a new job.
- Removing the worker: delete `app/jobs/`, `app/worker.py`, the job
  functions, the jobs migration, the `WORKER_*` settings,
  the `worker` Railway service, and the Redis compose service if nothing
  else uses it.
