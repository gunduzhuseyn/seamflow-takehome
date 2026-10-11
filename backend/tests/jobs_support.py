"""Helpers for the jobs tests: a trivial job, and rows in plain SQL."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.jobs.models import Job
from app.jobs.runner import run_job
from tests.tenant_support import insert_member, insert_org

Owner = tuple[uuid.UUID, uuid.UUID]

# The job kind and the arq function name of the test job.
KIND = "echo_subject"


async def work(job: Job, session: AsyncSession) -> dict[str, Any]:
    """The work of the test job. Tests monkeypatch it to fail or hang."""
    return {"subject_id": str(job.subject_id)}


async def echo_subject(ctx: dict[str, Any], job_id: str) -> None:
    """The arq function of the test job. `work` is read at call time."""
    await run_job(ctx, job_id, work)


def idempotency_key(subject_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"{KIND}:{subject_id}:{job_id}"


async def insert_job(
    session: AsyncSession,
    org_id: uuid.UUID,
    subject_id: uuid.UUID,
    *,
    status: str = "queued",
    attempts: int = 0,
    max_attempts: int = 3,
) -> uuid.UUID:
    job_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO jobs (id, org_id, kind, subject_id, idempotency_key, status, "
            "attempts, max_attempts, request_id, created_at) "
            "VALUES (:id, :org_id, :kind, :subject, :key, :status, :attempts, "
            ":max_attempts, 'req-seed', now())"
        ),
        {
            "id": job_id,
            "org_id": org_id,
            "kind": KIND,
            "subject": subject_id,
            "key": idempotency_key(subject_id, job_id),
            "status": status,
            "attempts": attempts,
            "max_attempts": max_attempts,
        },
    )
    return job_id


async def stored_jobs(
    session: AsyncSession, subject_id: uuid.UUID
) -> list[dict[str, Any]]:
    session.expire_all()
    result = await session.execute(
        text("SELECT * FROM jobs WHERE subject_id = :id ORDER BY created_at, id"),
        {"id": subject_id},
    )
    return [dict(row) for row in result.mappings().all()]


@pytest.fixture
def job_ctx(db_connection: AsyncConnection, settings: Settings) -> dict[str, Any]:
    """The context the worker startup builds, on the test connection."""
    sessionmaker = async_sessionmaker(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    return {"sessionmaker": sessionmaker, "settings": settings}


@pytest.fixture
async def owner(db_session: AsyncSession) -> Owner:
    org = await insert_org(db_session)
    user = await insert_member(db_session, org, "worker", "member")
    await db_session.commit()
    return org, user
