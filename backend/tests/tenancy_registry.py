"""Routes and a row factory for every org-scoped table.

The tenancy tests read this registry. A new table with an `org_id` column
needs an entry here, or an exemption with a reason.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# insert_row(session, org_id, user_id) -> id of one new row in that org.
RowFactory = Callable[[AsyncSession, uuid.UUID, uuid.UUID], Awaitable[uuid.UUID]]

ALL_METHODS = frozenset({"list", "get", "create", "patch", "delete"})


@dataclass(frozen=True)
class TenantRoutes:
    collection: str
    create_body: dict[str, object]
    update_body: dict[str, object]
    insert_row: RowFactory
    # The routes the table has. A read-only table lists only "get".
    methods: frozenset[str] = ALL_METHODS

    def item(self, row_id: uuid.UUID | str) -> str:
        return f"{self.collection}/{row_id}"


async def insert_llm_call(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    call_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO llm_calls (id, org_id, user_id, subject_id, request_id, "
            "prompt_name, prompt_version, model, status, created_at) "
            "VALUES (:id, :org_id, :user, :subject, 'req', 'classify', 1, "
            "'fake-model', 'running', now())"
        ),
        {"id": call_id, "org_id": org_id, "user": user_id, "subject": uuid.uuid4()},
    )
    return call_id


async def insert_job(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    subject_id = uuid.uuid4()
    job_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO jobs (id, org_id, kind, subject_id, idempotency_key, status, "
            "attempts, max_attempts, request_id, created_at) "
            "VALUES (:id, :org_id, 'echo_subject', :subject, :key, 'succeeded', 1, 3, "
            "'req', now())"
        ),
        {
            "id": job_id,
            "org_id": org_id,
            "subject": subject_id,
            "key": f"echo_subject:{subject_id}:{job_id}",
        },
    )
    return job_id


async def insert_classification(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    row_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO classifications (id, org_id, submitted_by, created_at, "
            "updated_at, filename, original_key, status, review_status, cost_usd) "
            "VALUES (:id, :org_id, :user, now(), now(), 'a.jpg', :key, 'queued', "
            "'not_required', 0)"
        ),
        {
            "id": row_id,
            "org_id": org_id,
            "user": user_id,
            "key": f"incoming/{org_id}/{row_id}",
        },
    )
    return row_id


REGISTRY: dict[str, TenantRoutes] = {
    # Written by the feature that runs a call. Only GET /llm-calls/{id} exists.
    "llm_calls": TenantRoutes(
        collection="/llm-calls",
        create_body={},
        update_body={},
        insert_row=insert_llm_call,
        methods=frozenset({"get"}),
    ),
    # Written by `start_job`, which acceptance/test_jobs.py covers.
    "jobs": TenantRoutes(
        collection="/jobs",
        create_body={},
        update_body={},
        insert_row=insert_job,
        methods=frozenset({"get"}),
    ),
    # Create needs a key under the caller's org and returns 202.
    # acceptance/test_classifications.py covers it.
    "classifications": TenantRoutes(
        collection="/classifications",
        create_body={},
        update_body={},
        insert_row=insert_classification,
        methods=frozenset({"list", "get"}),
    ),
}

# Tables with an org_id column that no route reads or writes by id.
EXEMPT: dict[str, str] = {
    "memberships": (
        "No route takes a membership id. /me reads only the caller's own "
        "memberships, and auth tests cover the active-org header."
    ),
}
