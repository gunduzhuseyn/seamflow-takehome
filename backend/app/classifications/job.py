"""The worker job: fetch the upload, check it, deduplicate, classify, write.

A check that fails ends the row as `failed` with an error code and the job
as succeeded, so arq does not run it again. Any other error raises, so the
runner retries; the last attempt ends the row as `failed` too. A cancelled
job (the arq timeout) ends the row as `failed` with `timeout`.
"""

import asyncio
import hashlib
import logging
import time
from decimal import Decimal
from functools import partial
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import images
from app.classifications.models import (
    MAX_UPLOAD_BYTES,
    Classification,
    ClassificationRepository,
    ClassificationStatus,
    ReviewStatus,
    Verdict,
)
from app.core.config import Settings
from app.jobs.models import Job
from app.jobs.runner import run_job
from app.llm.complete import LLMCallError
from app.llm.limits import InputTooLargeError
from app.llm.provider import LLMProvider
from app.storage.client import ObjectNotFoundError, Storage
from app.vision.classify import classify_image

log = logging.getLogger("app.classifications")

# Seconds between checks on the row of the same image that another job owns.
DUPLICATE_POLL_SECONDS = 0.5


async def classify_image_job(ctx: dict[str, Any], job_id: str) -> None:
    """The arq function. `ctx` has the sessionmaker, settings, storage, provider."""
    await run_job(ctx, job_id, partial(_work, ctx))


async def _work(ctx: dict[str, Any], job: Job, session: AsyncSession) -> dict[str, Any]:
    repository = ClassificationRepository(session)
    row = await repository.get(job.org_id, job.subject_id)
    if row is None:
        raise LookupError(f"classification {job.subject_id} not found")
    if row.verdict is not None:
        _log(row, "already classified")
        return {"outcome": "already_classified"}
    row.status = ClassificationStatus.processing
    row.job_id = job.id
    await session.commit()
    _log(row, "processing")
    row_id = row.id
    try:
        return await _process(ctx, session, repository, row, job)
    except asyncio.CancelledError:
        # arq cancels at job_timeout and at shutdown, and does not run the
        # job again. This session may be mid-statement, so a fresh one writes.
        sessionmaker: async_sessionmaker[AsyncSession] = ctx["sessionmaker"]
        async with sessionmaker() as fresh:
            await _mark_failed(fresh, row_id, "timeout")
        raise
    except LLMCallError as exc:
        await _fail_on_last_attempt(session, job, row_id, "provider_error", exc)
        raise
    except Exception as exc:
        await _fail_on_last_attempt(session, job, row_id, "worker_error", exc)
        raise


async def _process(
    ctx: dict[str, Any],
    session: AsyncSession,
    repository: ClassificationRepository,
    row: Classification,
    job: Job,
) -> dict[str, Any]:
    settings: Settings = ctx["settings"]
    storage: Storage = ctx["storage"]
    provider: LLMProvider = ctx["llm_provider"]
    clock = time.perf_counter()
    deadline = clock + settings.WORKER_JOB_TIMEOUT_SECONDS

    size = await storage.head(row.original_key)
    if size is None:
        return await _fail(session, row, "missing_object")
    if size > MAX_UPLOAD_BYTES:
        return await _fail(session, row, "too_large")
    try:
        data = await storage.get_bytes(row.original_key)
    except ObjectNotFoundError:
        return await _fail(session, row, "missing_object")
    try:
        info = images.inspect(data)
    except images.InvalidImage:
        return await _fail(session, row, "invalid_image")
    row.original_mime = info.mime
    row.original_bytes = size
    await session.commit()
    sha256 = hashlib.sha256(data).hexdigest()
    _log(row, "inspected")

    original = await _own_hash_or_find_original(
        session, repository, row, sha256, deadline
    )
    if original is not None:
        row.verdict = original.verdict
        row.confidence = original.confidence
        row.observations = original.observations
        row.thumbnail_key = original.thumbnail_key
        row.review_status = original.review_status
        row.final_verdict = original.final_verdict
        row.reviewed_by = original.reviewed_by
        row.reviewed_at = original.reviewed_at
        row.duplicate_of = original.id
        row.image_sha256 = sha256
        row.cost_usd = Decimal(0)
        row.status = ClassificationStatus.completed
        await session.commit()
        _log(row, "deduplicated", duplicate_of=str(original.id))
        return {"outcome": "duplicate", "duplicate_of": str(original.id)}

    try:
        thumbnail = images.thumbnail(data)
        model_input = images.model_input(data)
    except images.InvalidImage:
        return await _fail(session, row, "invalid_image")
    thumbnail_key = f"thumbs/{row.org_id}/{row.id}.webp"
    await storage.put_bytes(thumbnail_key, thumbnail, "image/webp")
    row.thumbnail_key = thumbnail_key
    await session.commit()
    _log(row, "thumbnail stored")

    try:
        outcome = await classify_image(
            session,
            provider,
            row.org_id,
            row.submitted_by,
            row.id,
            model_input,
            settings=settings,
        )
    except InputTooLargeError:
        return await _fail(session, row, "too_large")
    result = outcome.result
    row.verdict = Verdict(result.verdict)
    row.confidence = Decimal(f"{result.confidence:.3f}")
    row.observations = result.observations
    row.latency_ms = int((time.perf_counter() - clock) * 1000)
    row.cost_usd = outcome.cost_usd
    row.llm_call_id = outcome.llm_call_id
    row.review_status = (
        ReviewStatus.pending
        if result.confidence < settings.CLASSIFY_REVIEW_THRESHOLD
        else ReviewStatus.not_required
    )
    row.status = ClassificationStatus.completed
    await session.commit()
    _log(
        row,
        "classified",
        verdict=row.verdict,
        confidence=result.confidence,
        review_status=row.review_status,
    )
    return {"outcome": "classified", "verdict": row.verdict}


async def _own_hash_or_find_original(
    session: AsyncSession,
    repository: ClassificationRepository,
    row: Classification,
    sha256: str,
    deadline: float,
) -> Classification | None:
    """Take the hash for this row, or return the completed row that owns it.

    The partial unique index admits one owner per hash and org. While
    another job owns the hash, this one waits for it to complete, then
    copies it. A failed owner releases the hash.
    """
    org_id = row.org_id
    while True:
        original = await repository.find_duplicate(org_id, sha256)
        if original is not None:
            return original
        row.image_sha256 = sha256
        try:
            await session.commit()
            return None
        except IntegrityError:
            await session.rollback()
            # The rollback expired the row. Load it again before the next use.
            await session.refresh(row)
        if time.perf_counter() > deadline:
            raise TimeoutError("another job on the same image did not finish")
        _log(row, "waiting for the job on the same image")
        await _pause()


async def _pause() -> None:
    await asyncio.sleep(DUPLICATE_POLL_SECONDS)


async def _fail(
    session: AsyncSession, row: Classification, code: str
) -> dict[str, Any]:
    row.status = ClassificationStatus.failed
    row.error_code = code
    await session.commit()
    _log(row, "failed", error_code=code)
    return {"outcome": "failed", "error_code": code}


async def _fail_on_last_attempt(
    session: AsyncSession, job: Job, row_id: Any, code: str, exc: Exception
) -> None:
    # A database error leaves the transaction aborted. Roll back first.
    await session.rollback()
    log.info(
        "attempt failed",
        extra={
            "classification_id": str(row_id),
            "error": f"{type(exc).__name__}: {exc}",
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
        },
    )
    if job.attempts >= job.max_attempts:
        await _mark_failed(session, row_id, code)


async def _mark_failed(session: AsyncSession, row_id: Any, code: str) -> None:
    await session.execute(
        update(Classification)
        .where(Classification.id == row_id)
        .values(
            status=ClassificationStatus.failed, error_code=code, updated_at=func.now()
        )
    )
    await session.commit()
    log.info("failed", extra={"classification_id": str(row_id), "error_code": code})


def _log(row: Classification, message: str, **fields: object) -> None:
    # The formatter adds the request id from the context the runner set.
    log.info(message, extra={"classification_id": str(row.id), **fields})
