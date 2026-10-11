"""Run one job against its row: claim, do the work, write the end state.

The worker calls `run_job` with the arq context. `ctx["sessionmaker"]` and
`ctx["settings"]` come from the worker startup. The claim is one conditional
UPDATE from `queued` to `running`, so a second delivery of a finished or
running job returns without a change. After the claim, every write is a
statement; the ORM row is only a snapshot.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from arq.worker import Retry
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.request_id import request_id_var
from app.jobs.models import Job, JobStatus

log = logging.getLogger("app.jobs")

# Seconds before the next attempt, times the attempts so far.
RETRY_DELAY_SECONDS = 1

# work(job, session) -> the result to store on the row.
Work = Callable[[Job, AsyncSession], Awaitable[dict[str, Any]]]
Sessionmaker = async_sessionmaker[AsyncSession]


async def run_job(ctx: dict[str, Any], job_id: str, work: Work) -> None:
    sessionmaker: Sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        job = await _claim(session, uuid.UUID(job_id))
        if job is None:
            log.info("job not queued", extra={"job_id": job_id})
            return
        # Worker log lines carry the request that started the job.
        token = request_id_var.set(job.request_id)
        try:
            await _run(sessionmaker, session, job, work)
        finally:
            request_id_var.reset(token)


async def _claim(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Move the row from queued to running in one statement. None: not queued."""
    job = await session.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.queued)
        .values(
            status=JobStatus.running,
            attempts=Job.attempts + 1,
            started_at=func.coalesce(Job.started_at, func.now()),
        )
        .returning(Job)
    )
    await session.commit()
    if job is not None:
        # A snapshot. A later rollback must not expire it.
        session.expunge(job)
    return job


async def _run(
    sessionmaker: Sessionmaker, session: AsyncSession, job: Job, work: Work
) -> None:
    _log(job, "job started")
    try:
        result = await work(job, session)
    except asyncio.CancelledError:
        # arq cancels at job_timeout and at shutdown. arq does not run the
        # job again after a timeout, so the row ends failed either way. This
        # session may be mid-statement, so a fresh one writes the row.
        async with sessionmaker() as fresh:
            await _finish(fresh, job, JobStatus.failed, error="cancelled")
        _log(job, "job cancelled", status=JobStatus.failed)
        raise
    except Exception as exc:
        # A database error leaves the transaction aborted. Roll back first.
        await session.rollback()
        error = f"{type(exc).__name__}: {exc}"
        if job.attempts < job.max_attempts:
            await _finish(session, job, JobStatus.queued, error=error)
            _log(job, "job retry", status=JobStatus.queued)
            raise Retry(defer=RETRY_DELAY_SECONDS * job.attempts) from exc
        await _finish(session, job, JobStatus.failed, error=error)
        _log(job, "job failed", status=JobStatus.failed)
        raise
    await _finish(session, job, JobStatus.succeeded, result=result)
    _log(job, "job succeeded", status=JobStatus.succeeded)


async def _finish(
    session: AsyncSession,
    job: Job,
    status: JobStatus,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    values: dict[str, Any] = {"status": status, "result": result, "error": error}
    if status is not JobStatus.queued:
        values["finished_at"] = func.now()
    await session.execute(update(Job).where(Job.id == job.id).values(**values))
    await session.commit()


def _log(job: Job, message: str, status: JobStatus = JobStatus.running) -> None:
    log.info(
        message,
        extra={
            "job_id": str(job.id),
            "kind": job.kind,
            "status": status,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
        },
    )
