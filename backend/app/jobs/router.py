import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import OrgContext
from app.core.db import SessionDep
from app.jobs.models import JobRepository, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_id: uuid.UUID
    kind: str
    status: JobStatus
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None
    request_id: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.get("/{job_id}", name="get")
async def get_job(
    session: SessionDep, context: OrgContext, job_id: uuid.UUID
) -> JobOut:
    job = await JobRepository(session).get(context.org.id, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobOut.model_validate(job)
