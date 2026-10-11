"""The job function: idempotent runs, bounded retries, cancellation."""

import asyncio
import uuid
from typing import Any

import pytest
from arq.worker import Retry
from sqlalchemy.ext.asyncio import AsyncSession

import tests.jobs_support as jobs_support
from tests.jobs_support import (
    Owner,
    echo_subject,
    insert_job,
    job_ctx,
    owner,
    stored_jobs,
)

__all__ = ["job_ctx", "owner"]


async def _boom(job: Any, session: Any) -> dict[str, Any]:
    raise RuntimeError("boom")


async def test_job_writes_the_result_once_and_a_second_run_changes_nothing(
    db_session: AsyncSession, job_ctx: dict[str, Any], owner: Owner
) -> None:
    org, _ = owner
    subject_id = uuid.uuid4()
    job_id = await insert_job(db_session, org, subject_id)
    await db_session.commit()

    await echo_subject(job_ctx, str(job_id))

    (first,) = await stored_jobs(db_session, subject_id)
    assert first["status"] == "succeeded"
    assert first["result"] == {"subject_id": str(subject_id)}
    assert first["attempts"] == 1
    assert first["error"] is None
    assert first["started_at"] is not None and first["finished_at"] is not None
    assert first["started_at"] <= first["finished_at"]

    await echo_subject(job_ctx, str(job_id))

    (second,) = await stored_jobs(db_session, subject_id)
    assert second == first

    # A row another worker holds is not run either.
    held_subject = uuid.uuid4()
    await insert_job(db_session, org, held_subject, status="running", attempts=1)
    await db_session.commit()
    (before,) = await stored_jobs(db_session, held_subject)

    await echo_subject(job_ctx, str(before["id"]))

    assert await stored_jobs(db_session, held_subject) == [before]
    assert before["result"] is None


async def test_cancelled_job_is_stored_as_failed(
    db_session: AsyncSession,
    job_ctx: dict[str, Any],
    owner: Owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """arq cancels the coroutine at job_timeout. The row must not stay running."""
    org, _ = owner
    subject_id = uuid.uuid4()
    job_id = await insert_job(db_session, org, subject_id)
    await db_session.commit()

    async def slow(job: Any, session: Any) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {}

    monkeypatch.setattr(jobs_support, "work", slow)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(echo_subject(job_ctx, str(job_id)), timeout=0.2)

    (row,) = await stored_jobs(db_session, subject_id)
    assert (row["status"], row["attempts"]) == ("failed", 1)
    assert row["error"] == "cancelled"
    assert row["result"] is None
    assert row["started_at"] is not None and row["finished_at"] is not None


async def test_failing_job_retries_until_max_attempts_then_fails(
    db_session: AsyncSession,
    job_ctx: dict[str, Any],
    owner: Owner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _ = owner
    subject_id = uuid.uuid4()
    job_id = await insert_job(db_session, org, subject_id, max_attempts=3)
    await db_session.commit()
    monkeypatch.setattr(jobs_support, "work", _boom)

    for attempt in (1, 2):
        with pytest.raises(Retry):
            await echo_subject(job_ctx, str(job_id))
        (row,) = await stored_jobs(db_session, subject_id)
        assert (row["status"], row["attempts"]) == ("queued", attempt)
        assert row["error"] == "RuntimeError: boom"
        assert row["finished_at"] is None

    with pytest.raises(RuntimeError, match="boom"):
        await echo_subject(job_ctx, str(job_id))

    (failed,) = await stored_jobs(db_session, subject_id)
    assert (failed["status"], failed["attempts"]) == ("failed", 3)
    assert failed["error"] == "RuntimeError: boom"
    assert failed["result"] is None
    assert failed["finished_at"] is not None

    # A run after the final failure changes nothing.
    await echo_subject(job_ctx, str(job_id))
    assert await stored_jobs(db_session, subject_id) == [failed]
