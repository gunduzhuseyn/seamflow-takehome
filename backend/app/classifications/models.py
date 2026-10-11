"""One row per submitted image. The API inserts it, the worker fills it in.

`jobs` and `llm_calls` link back through their `subject_id`, which holds
the classification id.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.repository import OrgScoped, Repository

# The declared size at POST /uploads and the HEAD size in the worker.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# The job kind and the arq function name.
JOB_KIND = "classify_image"


class ClassificationStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ReviewStatus(StrEnum):
    not_required = "not_required"
    pending = "pending"
    reviewed = "reviewed"


class Verdict(StrEnum):
    match = "match"
    no_match = "no_match"


# The question the model answers when the request names none.
DEFAULT_QUESTION_LABEL = "hot dog"


def _now() -> datetime:
    return datetime.now(UTC)


def _enum[E: StrEnum](kind: type[E], name: str) -> Enum:
    # Text with a check constraint, not a Postgres enum type, so a new
    # value is an expand-only migration. The name keys the constraint.
    return Enum(kind, native_enum=False, create_constraint=True, length=16, name=name)


class Classification(OrgScoped):
    __tablename__ = "classifications"
    __table_args__ = (
        Index("ix_classifications_org_id_created_at", "org_id", "created_at"),
        Index("ix_classifications_org_id_image_sha256", "org_id", "image_sha256"),
        Index("ix_classifications_org_id_review_status", "org_id", "review_status"),
        # One row owns a hash and a question in an org: the one the model
        # classifies. A second job on the same pair waits for it, then
        # copies it.
        Index(
            "uq_classifications_hash_owner",
            "org_id",
            "image_sha256",
            "question_label",
            unique=True,
            postgresql_where=text(
                "duplicate_of IS NULL AND status IN ('processing', 'completed')"
            ),
        ),
    )

    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Set in Python, so rows in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # As uploaded. Display only.
    filename: Mapped[str] = mapped_column(Text)
    original_key: Mapped[str] = mapped_column(Text)
    # The worker sets these from the magic bytes and the HEAD.
    original_mime: Mapped[str | None] = mapped_column(Text)
    original_bytes: Mapped[int | None] = mapped_column(Integer)
    image_sha256: Mapped[str | None] = mapped_column(Text)
    # 320 px WebP in storage.
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    # Trimmed and lower-cased. "Is this a {question_label}?"
    question_label: Mapped[str] = mapped_column(
        Text, default=DEFAULT_QUESTION_LABEL, server_default=DEFAULT_QUESTION_LABEL
    )
    status: Mapped[ClassificationStatus] = mapped_column(
        _enum(ClassificationStatus, "classification_status")
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status")
    )
    verdict: Mapped[Verdict | None] = mapped_column(_enum(Verdict, "verdict"))
    # 0 to 1.
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    # Under 300 characters.
    observations: Mapped[str | None] = mapped_column(Text)
    # Set by a reviewer.
    final_verdict: Mapped[Verdict | None] = mapped_column(
        _enum(Verdict, "final_verdict")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Worker measured, download to result.
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # 0 when deduplicated.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(0))
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column()
    job_id: Mapped[uuid.UUID | None] = mapped_column()
    # The earlier row with the same hash.
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column()
    # Set when status is failed.
    error_code: Mapped[str | None] = mapped_column(Text)


class ClassificationRepository(Repository[Classification]):
    model = Classification

    async def list_filtered(
        self,
        org_id: uuid.UUID,
        *,
        status: ClassificationStatus | None = None,
        review_status: ReviewStatus | None = None,
        verdict: Verdict | None = None,
        limit: int,
    ) -> tuple[Sequence[Classification], int]:
        """The newest `limit` rows that match, and the count of every match."""
        conditions = [Classification.org_id == org_id]
        if status is not None:
            conditions.append(Classification.status == status)
        if review_status is not None:
            conditions.append(Classification.review_status == review_status)
        if verdict is not None:
            conditions.append(Classification.verdict == verdict)
        total = await self.session.scalar(
            select(func.count()).select_from(Classification).where(*conditions)
        )
        rows = await self.session.scalars(
            select(Classification)
            .where(*conditions)
            .order_by(Classification.created_at.desc(), Classification.id.desc())
            .limit(limit)
        )
        return rows.all(), total or 0

    async def find_duplicate(
        self, org_id: uuid.UUID, sha256: str, question_label: str
    ) -> Classification | None:
        """The earliest completed row with the hash and the question, not a copy."""
        return await self.session.scalar(
            select(Classification)
            .where(
                Classification.org_id == org_id,
                Classification.image_sha256 == sha256,
                Classification.question_label == question_label,
                Classification.status == ClassificationStatus.completed,
                Classification.duplicate_of.is_(None),
            )
            .order_by(Classification.created_at, Classification.id)
            .limit(1)
        )
