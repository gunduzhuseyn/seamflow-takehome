"""One burst worker on the real Redis: two jobs, one retry, both terminal."""

import uuid
from typing import Any

import pytest
from arq import ArqRedis
from arq.constants import health_check_key_suffix
from arq.worker import Worker
from sqlalchemy.ext.asyncio import AsyncSession

import tests.jobs_support as jobs_support
from app.core.config import Settings
from tests.jobs_support import (
    KIND,
    Owner,
    echo_subject,
    idempotency_key,
    insert_job,
    job_ctx,
    owner,
    stored_jobs,
)

__all__ = ["job_ctx", "owner"]


async def test_burst_worker_finishes_both_jobs_and_retries_the_failing_one(
    db_session: AsyncSession,
    job_ctx: dict[str, Any],
    arq_pool: ArqRedis,
    settings: Settings,
    owner: Owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _ = owner
    steady = uuid.uuid4()
    flaky = uuid.uuid4()
    steady_job = await insert_job(db_session, org, steady)
    flaky_job = await insert_job(db_session, org, flaky)
    await db_session.commit()
    real_work = jobs_support.work
    failures: list[uuid.UUID] = []

    async def fail_once(job: Any, session: Any) -> dict[str, Any]:
        if job.subject_id == flaky and not failures:
            failures.append(job.subject_id)
            raise RuntimeError("flaky")
        return await real_work(job, session)

    monkeypatch.setattr(jobs_support, "work", fail_once)
    # Its own queue: the acceptance tests leave jobs on the run's queue.
    queue = f"{settings.WORKER_QUEUE_NAME}:burst"
    for subject_id, job_id in ((steady, steady_job), (flaky, flaky_job)):
        enqueued = await arq_pool.enqueue_job(
            KIND,
            str(job_id),
            _job_id=idempotency_key(subject_id, job_id),
            _queue_name=queue,
        )
        assert enqueued is not None
    worker = Worker(
        functions=[echo_subject],
        redis_pool=arq_pool,
        queue_name=queue,
        ctx=job_ctx,
        burst=True,
        # One connection in the test, so one job at a time.
        max_jobs=1,
        poll_delay=0.05,
        keep_result=0,
        handle_signals=False,
        max_tries=settings.WORKER_MAX_ATTEMPTS,
        job_timeout=settings.WORKER_JOB_TIMEOUT_SECONDS,
    )

    try:
        completed = await worker.run_check()
    finally:
        await arq_pool.delete(queue, queue + health_check_key_suffix)

    assert completed == 2
    assert (worker.jobs_retried, worker.jobs_failed) == (1, 0)
    (steady_row,) = await stored_jobs(db_session, steady)
    assert (steady_row["status"], steady_row["attempts"]) == ("succeeded", 1)
    assert steady_row["result"] == {"subject_id": str(steady)}
    (flaky_row,) = await stored_jobs(db_session, flaky)
    assert (flaky_row["status"], flaky_row["attempts"]) == ("succeeded", 2)
    assert flaky_row["result"] == {"subject_id": str(flaky)}
    assert flaky_row["error"] is None
