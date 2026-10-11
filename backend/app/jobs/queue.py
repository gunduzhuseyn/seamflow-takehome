"""Insert a job row and put the job on the arq queue."""

import uuid
from datetime import UTC, datetime

from arq import ArqRedis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import current_request_id
from app.jobs.models import Job, JobRepository, JobStatus


class ActiveJobError(Exception):
    """A queued or running job of this kind exists for the subject."""


async def start_job(
    session: AsyncSession,
    pool: ArqRedis,
    *,
    org_id: uuid.UUID,
    subject_id: uuid.UUID,
    kind: str,
    max_attempts: int,
) -> Job:
    """Commit a queued row, then enqueue it. `kind` is the arq function name.

    The check gives the plain 409. The partial unique index on the table
    catches two requests that pass the check at the same time.
    """
    repository = JobRepository(session)
    if await repository.active(org_id, subject_id, kind) is not None:
        raise ActiveJobError
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        org_id=org_id,
        kind=kind,
        subject_id=subject_id,
        idempotency_key=f"{kind}:{subject_id}:{job_id}",
        status=JobStatus.queued,
        attempts=0,
        max_attempts=max_attempts,
        request_id=current_request_id(),
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise ActiveJobError from None
    # Committed before the enqueue, so the worker finds the row.
    await session.commit()
    try:
        await pool.enqueue_job(kind, str(job.id), _job_id=job.idempotency_key)
    except Exception as exc:
        # The row must not stay queued with nothing on the queue.
        job.status = JobStatus.failed
        job.error = f"enqueue failed: {type(exc).__name__}: {exc}"
        job.finished_at = datetime.now(UTC)
        await session.commit()
        raise
    return job
