"""Uploads and classifications: presign, create and start the job, list, get,
review, metrics, CSV export."""

import csv
import io
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import OrgContext
from app.auth.models import User
from app.classifications.models import (
    DEFAULT_QUESTION_LABEL,
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
MAX_LABELS = 50
CSV_FILENAME = "classifications.csv"
CSV_COLUMNS = (
    "id",
    "created_at",
    "filename",
    "submitted_by",
    "question_label",
    "verdict",
    "final_verdict",
    "confidence",
    "status",
    "review_status",
    "latency_ms",
    "cost_usd",
    "duplicate_of",
)
# The question is untrusted data that reaches the model. Only a short name
# of a thing passes: no punctuation, newlines, braces, or angle brackets.
QUESTION_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 '\-]{1,59}$")
QUESTION_LABEL_BANNED_WORDS = ("ignore", "instruction", "system", "assistant", "prompt")
QUESTION_LABEL_DETAIL = (
    "The question is 2 to 60 characters: letters, digits, spaces, "
    "apostrophes, and hyphens."
)


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
    # "Is this a {question_label}?" Trimmed and lower-cased, then
    # `check_question_label` runs in the route.
    question_label: Annotated[
        str, StringConstraints(strip_whitespace=True, to_lower=True)
    ] = DEFAULT_QUESTION_LABEL


# The list and export filter: an exact match on the stored, lower-cased label.
QuestionLabelQuery = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=1),
    Query(),
]


def check_question_label(label: str) -> None:
    """400 unless the label is a plain name of a thing."""
    if not QUESTION_LABEL_PATTERN.fullmatch(label) or any(
        word in label for word in QUESTION_LABEL_BANNED_WORDS
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=QUESTION_LABEL_DETAIL)


class VerdictLabels(BaseModel):
    match: str
    no_match: str


def verdict_labels(question_label: str) -> VerdictLabels:
    """The display text of each verdict: "Hot Dog" and "Not Hot Dog" for "hot dog"."""
    title = question_label.title()
    return VerdictLabels(match=title, no_match=f"Not {title}")


class ClassificationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    filename: str
    submitted_by_name: str
    question_label: str
    # The display text of each verdict value, from the question.
    verdict_labels: VerdictLabels
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


class ReviewCreate(BaseModel):
    final_verdict: Verdict


class MetricsOut(BaseModel):
    total: int
    completed: int
    match: int
    no_match: int
    pending_review: int
    reviewed: int
    # Reviewed rows whose final verdict differs from the model verdict.
    overrides: int
    # overrides over reviewed. 0 when nothing is reviewed.
    override_rate: float
    # Over completed rows with a latency. Null when there are none.
    avg_latency_ms: float | None
    total_cost_usd: float
    deduplicated: int


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
                question_label=row.question_label,
                verdict_labels=verdict_labels(row.question_label),
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
    check_question_label(body.question_label)
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
        question_label=body.question_label,
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
    offset: Annotated[int, Query(ge=0)] = 0,
    status: ClassificationStatus | None = None,
    review_status: ReviewStatus | None = None,
    verdict: Verdict | None = None,
    question_label: QuestionLabelQuery = None,
) -> ClassificationList:
    rows, total = await ClassificationRepository(session).list_filtered(
        context.org.id,
        status=status,
        review_status=review_status,
        verdict=verdict,
        question_label=question_label,
        limit=limit,
        offset=offset,
    )
    return ClassificationList(
        items=await _to_out(session, storage, list(rows)), total=total
    )


def _csv_lines(
    rows: list[Classification], names: dict[uuid.UUID, str]
) -> Iterator[str]:
    """The header, then one line per row. Every value is loaded before the first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat(),
                row.filename,
                names.get(row.submitted_by, ""),
                row.question_label,
                row.verdict,
                row.final_verdict,
                row.confidence,
                row.status,
                row.review_status,
                row.latency_ms,
                row.cost_usd,
                row.duplicate_of,
            ]
        )
        yield buffer.getvalue()


# The fixed paths come before `/classifications/{classification_id}`, or
# FastAPI reads "metrics" as an id.
@router.get("/classifications/metrics", name="metrics")
async def get_metrics(session: SessionDep, context: OrgContext) -> MetricsOut:
    metrics = await ClassificationRepository(session).metrics(context.org.id)
    return MetricsOut(
        total=metrics.total,
        completed=metrics.completed,
        match=metrics.match,
        no_match=metrics.no_match,
        pending_review=metrics.pending_review,
        reviewed=metrics.reviewed,
        overrides=metrics.overrides,
        override_rate=(
            metrics.overrides / metrics.reviewed if metrics.reviewed else 0.0
        ),
        avg_latency_ms=metrics.avg_latency_ms,
        total_cost_usd=float(metrics.total_cost_usd),
        deduplicated=metrics.deduplicated,
    )


@router.get("/classifications/labels", name="labels")
async def list_labels(session: SessionDep, context: OrgContext) -> list[str]:
    """The distinct questions of the caller's org, most recently used first."""
    labels = await ClassificationRepository(session).labels(
        context.org.id, limit=MAX_LABELS
    )
    return list(labels)


@router.get(
    "/classifications/export.csv",
    name="export_csv",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_classifications_csv(
    session: SessionDep,
    context: OrgContext,
    status: ClassificationStatus | None = None,
    review_status: ReviewStatus | None = None,
    verdict: Verdict | None = None,
    question_label: QuestionLabelQuery = None,
) -> StreamingResponse:
    """Every row that matches the list filters, newest first."""
    rows, _ = await ClassificationRepository(session).list_filtered(
        context.org.id,
        status=status,
        review_status=review_status,
        verdict=verdict,
        question_label=question_label,
        limit=None,
    )
    names = await _names(session, list(rows))
    return StreamingResponse(
        _csv_lines(list(rows), names),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{CSV_FILENAME}"'},
    )


@router.post("/classifications/{classification_id}/review", name="review")
async def review_classification(
    body: ReviewCreate,
    session: SessionDep,
    context: OrgContext,
    storage: StorageDep,
    classification_id: uuid.UUID,
) -> ClassificationOut:
    """Confirm or override the model verdict of a completed row."""
    row = await ClassificationRepository(session).get(context.org.id, classification_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Classification not found"
        )
    if row.status != ClassificationStatus.completed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Only a completed classification can be reviewed.",
        )
    if row.review_status == ReviewStatus.reviewed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This classification already has a final verdict.",
        )
    row.final_verdict = body.final_verdict
    row.reviewed_by = context.user.id
    row.reviewed_at = datetime.now(UTC)
    row.review_status = ReviewStatus.reviewed
    await session.commit()
    (out,) = await _to_out(session, storage, [row])
    return out


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
