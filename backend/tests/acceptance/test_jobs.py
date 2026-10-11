"""Start a job: one queued row per call, one active per subject, org-scoped reads."""

import uuid

import pytest
from arq import ArqRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.request_id import request_id_var
from app.jobs.models import JobRepository
from app.jobs.queue import ActiveJobError, start_job
from tests.fakes import TokenFactory
from tests.jobs_support import KIND, insert_job, stored_jobs
from tests.tenant_support import (
    Tenant,
    auth_headers,
    insert_member,
    insert_org,
    tenant,
)

__all__ = ["tenant"]


@pytest.fixture(autouse=True)
def _queue(arq_pool: ArqRedis) -> None:
    """Every test here enqueues. The pool fixture deletes this run's keys."""


async def _start(
    session: AsyncSession,
    pool: ArqRedis,
    settings: Settings,
    org_id: uuid.UUID,
    subject_id: uuid.UUID,
) -> uuid.UUID:
    """Start a job and return its id. `stored_jobs` expires the ORM row later."""
    job = await start_job(
        session,
        pool,
        org_id=org_id,
        subject_id=subject_id,
        kind=KIND,
        max_attempts=settings.WORKER_MAX_ATTEMPTS,
    )
    return job.id


async def test_start_job_creates_a_queued_row_with_the_request_id(
    client: AsyncClient,
    db_session: AsyncSession,
    arq_pool: ArqRedis,
    settings: Settings,
    tenant: Tenant,
) -> None:
    org, _, headers = tenant
    subject_id = uuid.uuid4()

    # The request id middleware sets the contextvar; this test sets it by hand.
    token = request_id_var.set("req-job-1")
    try:
        job_id = await _start(db_session, arq_pool, settings, org, subject_id)
    finally:
        request_id_var.reset(token)

    (row,) = await stored_jobs(db_session, subject_id)
    assert row["id"] == job_id
    assert (row["org_id"], row["subject_id"], row["kind"]) == (org, subject_id, KIND)
    assert row["status"] == "queued"
    assert (row["attempts"], row["max_attempts"]) == (0, settings.WORKER_MAX_ATTEMPTS)
    assert row["request_id"] == "req-job-1"
    assert row["idempotency_key"] == f"{KIND}:{subject_id}:{job_id}"
    assert row["result"] is None and row["error"] is None
    assert row["created_at"] is not None
    assert row["started_at"] is None and row["finished_at"] is None
    # The job is on this run's queue under its idempotency key.
    score = await arq_pool.zscore(settings.WORKER_QUEUE_NAME, row["idempotency_key"])
    assert score is not None

    fetched = await client.get(f"/jobs/{job_id}", headers=headers)
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == str(job_id)
    assert body["subject_id"] == str(subject_id)
    assert (body["kind"], body["status"]) == (KIND, "queued")
    assert body["request_id"] == "req-job-1"
    assert body["result"] is None and body["error"] is None


async def test_second_start_while_a_job_is_active_raises_and_adds_no_row(
    db_session: AsyncSession, arq_pool: ArqRedis, settings: Settings, tenant: Tenant
) -> None:
    org, _, _ = tenant
    subject_id = uuid.uuid4()

    first = await _start(db_session, arq_pool, settings, org, subject_id)
    with pytest.raises(ActiveJobError):
        await _start(db_session, arq_pool, settings, org, subject_id)

    rows = await stored_jobs(db_session, subject_id)
    assert [row["id"] for row in rows] == [first]

    running_subject = uuid.uuid4()
    await insert_job(db_session, org, running_subject, status="running", attempts=1)
    await db_session.commit()

    with pytest.raises(ActiveJobError):
        await _start(db_session, arq_pool, settings, org, running_subject)

    assert len(await stored_jobs(db_session, running_subject)) == 1


async def test_start_after_a_finished_job_adds_a_row_and_latest_lists_it(
    db_session: AsyncSession, arq_pool: ArqRedis, settings: Settings, tenant: Tenant
) -> None:
    org, _, _ = tenant
    subject_id = uuid.uuid4()
    old = await insert_job(db_session, org, subject_id, status="failed", attempts=3)
    await db_session.commit()

    job_id = await _start(db_session, arq_pool, settings, org, subject_id)
    latest = await JobRepository(db_session).latest_per_kind(org, subject_id)
    latest_ids = [item.id for item in latest]

    rows = await stored_jobs(db_session, subject_id)
    assert [row["id"] for row in rows] == [old, job_id]
    assert latest_ids == [job_id]


async def test_foreign_job_is_404_and_own_job_is_200(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    tenant: Tenant,
) -> None:
    org, _, headers = tenant
    other_org = await insert_org(db_session, slug="other")
    await insert_member(db_session, other_org, "other", "admin")
    foreign_job = await insert_job(db_session, other_org, uuid.uuid4(), status="failed")
    await db_session.commit()

    foreign = await client.get(f"/jobs/{foreign_job}", headers=headers)
    missing = await client.get(f"/jobs/{uuid.uuid4()}", headers=headers)
    own = await client.get(
        f"/jobs/{foreign_job}", headers=auth_headers(make_token, "other")
    )

    assert (foreign.status_code, missing.status_code) == (404, 404)
    assert own.status_code == 200
    assert org != other_org
