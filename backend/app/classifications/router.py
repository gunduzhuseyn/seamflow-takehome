"""Uploads and classifications: presign, create and start the job, list, get."""

import uuid
from datetime import datetime
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import OrgContext
from app.auth.models import User
from app.classifications.models import (
    JOB_KIND,
    MAX_UPLOAD_BYTES,
    Classification,
    ClassificationRepository,
    ClassificationStatus,
    ReviewStatus,
    Verdict,
)
from app.core.config import Settings
from app.core.db import SessionDep
from app.jobs.queue import start_job
from app.llm.limits import enforce_rate_limit
from app.storage.client import Storage, StorageDep

router = APIRouter(tags=["classifications"])

ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)
UPLOAD_URL_EXPIRES_SECONDS = 600
THUMBNAIL_URL_EXPIRES_SECONDS = 3600
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int


class UploadOut(BaseModel):
    key: str
    upload_url: str
    expires_in: int


class ClassificationCreate(BaseModel):
    key: str = Field(min_length=1, max_length=512)
    filename: str = Field(min_length=1, max_length=255)


class ClassificationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    filename: str
    submitted_by_name: str
    status: ClassificationStatus
    review_status: ReviewStatus
    verdict: Verdict | None
    # Floats for the browser. The row keeps the exact numerics.
    confidence: float | None
    observations: str | None
    final_verdict: Verdict | None
    reviewed_at: datetime | None
    latency_ms: int | None
    cost_usd: float
    duplicate_of: uuid.UUID | None
    thumbnail_url: str | None
    error_code: str | None


class ClassificationList(BaseModel):
    items: list[ClassificationOut]
    total: int


def _upload_prefix(org_id: uuid.UUID) -> str:
    return f"incoming/{org_id}/"


def _display_name(email: str) -> str:
    return email.split("@", 1)[0]


async def _names(
    session: AsyncSession, rows: list[Classification]
) -> dict[uuid.UUID, str]:
    ids = {row.submitted_by for row in rows}
    if not ids:
        return {}
    result = await session.execute(select(User.id, User.email).where(User.id.in_(ids)))
    return {user_id: _display_name(email) for user_id, email in result.all()}


async def _to_out(
    session: AsyncSession, storage: Storage, rows: list[Classification]
) -> list[ClassificationOut]:
    names = await _names(session, rows)
    out: list[ClassificationOut] = []
    for row in rows:
        thumbnail_url = (
            await storage.presign_get(row.thumbnail_key, THUMBNAIL_URL_EXPIRES_SECONDS)
            if row.thumbnail_key
            else None
        )
        out.append(
            ClassificationOut(
                id=row.id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                filename=row.filename,
                submitted_by_name=names.get(row.submitted_by, ""),
                status=row.status,
                review_status=row.review_status,
                verdict=row.verdict,
                confidence=None if row.confidence is None else float(row.confidence),
                observations=row.observations,
                final_verdict=row.final_verdict,
                reviewed_at=row.reviewed_at,
                latency_ms=row.latency_ms,
                cost_usd=float(row.cost_usd),
                duplicate_of=row.duplicate_of,
                thumbnail_url=thumbnail_url,
                error_code=row.error_code,
            )
        )
    return out


@router.post("/uploads", name="create_upload", status_code=status.HTTP_201_CREATED)
async def create_upload(
    body: UploadCreate, context: OrgContext, storage: StorageDep
) -> UploadOut:
    if body.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, WebP, and GIF images are accepted.",
        )
    if body.size_bytes < 1 or body.size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Images must be 10 MB or smaller."
        )
    key = f"{_upload_prefix(context.org.id)}{uuid.uuid4()}"
    upload_url = await storage.presign_put(
        key, body.content_type, UPLOAD_URL_EXPIRES_SECONDS
    )
    return UploadOut(
        key=key, upload_url=upload_url, expires_in=UPLOAD_URL_EXPIRES_SECONDS
    )


@router.post("/classifications", name="create", status_code=status.HTTP_202_ACCEPTED)
async def create_classification(
    request: Request,
    body: ClassificationCreate,
    session: SessionDep,
    context: OrgContext,
    storage: StorageDep,
) -> ClassificationOut:
    if not body.key.startswith(_upload_prefix(context.org.id)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="The key is not an upload of this org."
        )
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    pool: ArqRedis = request.app.state.arq
    await enforce_rate_limit(redis, context.user.id, settings.LLM_RATE_LIMIT_PER_MINUTE)
    repository = ClassificationRepository(session)
    row = await repository.create(
        context.org.id,
        submitted_by=context.user.id,
        filename=body.filename,
        original_key=body.key,
        status=ClassificationStatus.queued,
        review_status=ReviewStatus.not_required,
    )
    try:
        # Commits the row with the job, then enqueues.
        job = await start_job(
            session,
            pool,
            org_id=context.org.id,
            subject_id=row.id,
            kind=JOB_KIND,
            max_attempts=settings.WORKER_MAX_ATTEMPTS,
        )
    except Exception:
        row.status = ClassificationStatus.failed
        row.error_code = "enqueue_failed"
        await session.commit()
        raise
    row.job_id = job.id
    await session.commit()
    (out,) = await _to_out(session, storage, [row])
    return out


@router.get("/classifications", name="list")
async def list_classifications(
    session: SessionDep,
    context: OrgContext,
    storage: StorageDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    status: ClassificationStatus | None = None,
    review_status: ReviewStatus | None = None,
    verdict: Verdict | None = None,
) -> ClassificationList:
    rows, total = await ClassificationRepository(session).list_filtered(
        context.org.id,
        status=status,
        review_status=review_status,
        verdict=verdict,
        limit=limit,
    )
    return ClassificationList(
        items=await _to_out(session, storage, list(rows)), total=total
    )


@router.get("/classifications/{classification_id}", name="get")
async def get_classification(
    session: SessionDep,
    context: OrgContext,
    storage: StorageDep,
    classification_id: uuid.UUID,
) -> ClassificationOut:
    row = await ClassificationRepository(session).get(context.org.id, classification_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Classification not found"
        )
    (out,) = await _to_out(session, storage, [row])
    return out
