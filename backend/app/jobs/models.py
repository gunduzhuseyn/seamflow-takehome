"""One row per background job. The API inserts it, the worker finishes it."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, distinct_on
from sqlalchemy.orm import Mapped, mapped_column

from app.core.repository import OrgScoped, Repository


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


# A job in one of these states blocks a new job of the same kind on the subject.
ACTIVE = (JobStatus.queued, JobStatus.running)


def _now() -> datetime:
    return datetime.now(UTC)


class Job(OrgScoped):
    __tablename__ = "jobs"
    __table_args__ = (
        # The one-active-job rule, enforced by the database. See decisions/0007.
        Index(
            "ix_jobs_active_per_subject",
            "kind",
            "subject_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    # Also the name of the arq function.
    kind: Mapped[str] = mapped_column(String(64))
    # The row the job works on. No foreign key: each kind names its own table.
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # `{kind}:{subject_id}:{id}`. The arq job id, so a second enqueue is a no-op.
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, create_constraint=True, length=16)
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    error: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(128))
    # Set in Python, so two jobs in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobRepository(Repository[Job]):
    model = Job

    async def active(
        self, org_id: uuid.UUID, subject_id: uuid.UUID, kind: str
    ) -> Job | None:
        return await self.session.scalar(
            select(Job).where(
                Job.org_id == org_id,
                Job.subject_id == subject_id,
                Job.kind == kind,
                Job.status.in_(ACTIVE),
            )
        )

    async def latest_per_kind(
        self, org_id: uuid.UUID, subject_id: uuid.UUID
    ) -> Sequence[Job]:
        """The newest job of each kind for the subject. Postgres DISTINCT ON."""
        result = await self.session.scalars(
            select(Job)
            .ext(distinct_on(Job.kind))
            .where(Job.org_id == org_id, Job.subject_id == subject_id)
            .order_by(Job.kind, Job.created_at.desc(), Job.id)
        )
        return result.all()
