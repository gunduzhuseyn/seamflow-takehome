"""Uploads and classifications: validation, create, the job inline, list."""

import asyncio
import hashlib
import uuid
from io import BytesIO
from typing import Any

import pytest
from arq import ArqRedis
from arq.constants import health_check_key_suffix
from arq.worker import Retry, Worker
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

import app.classifications.job as job_module
from app.classifications.job import classify_image_job
from app.classifications.models import JOB_KIND
from app.core.config import Settings
from app.llm.complete import LLMCallError
from app.llm.fake_provider import FakeProvider
from app.worker import WorkerSettings
from tests.fakes import FakeStorage
from tests.jobs_support import job_ctx
from tests.tenancy_registry import insert_classification
from tests.tenant_support import Tenant, tenant

__all__ = ["job_ctx", "tenant"]

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@pytest.fixture(autouse=True)
def _queue(arq_pool: ArqRedis) -> None:
    """Every create here enqueues. The pool fixture deletes this run's keys."""


@pytest.fixture
def worker_ctx(job_ctx: dict[str, Any], fake_storage: FakeStorage) -> dict[str, Any]:
    """The worker context with the fakes. Tests switch the provider fixture."""
    return {
        **job_ctx,
        "storage": fake_storage,
        "llm_provider": FakeProvider(fixture="hotdog"),
    }


def jpeg(color: tuple[int, int, int] = (200, 80, 20)) -> bytes:
    image = Image.new("RGB", (64, 48), color=color)
    out = BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


async def submit(
    client: AsyncClient,
    headers: dict[str, str],
    storage: FakeStorage,
    data: bytes | None,
    filename: str = "lunch.jpg",
) -> dict[str, Any]:
    """Presign, put the bytes in the fake store (None: skip), create the row."""
    upload = await client.post(
        "/uploads",
        headers=headers,
        json={"filename": filename, "content_type": "image/jpeg", "size_bytes": 1234},
    )
    assert upload.status_code == 201
    key = upload.json()["key"]
    if data is not None:
        storage.objects[key] = (data, "image/jpeg")
    created = await client.post(
        "/classifications", headers=headers, json={"key": key, "filename": filename}
    )
    assert created.status_code == 202, created.text
    return created.json()


async def stored(session: AsyncSession, table: str, column: str, value: uuid.UUID):
    session.expire_all()
    result = await session.execute(
        text(f"SELECT * FROM {table} WHERE {column} = :v ORDER BY created_at"),  # noqa: S608
        {"v": value},
    )
    return [dict(row) for row in result.mappings().all()]


async def run(
    ctx: dict[str, Any], session: AsyncSession, classification_id: str
) -> None:
    """Run the newest job of the classification inline, as the worker would."""
    jobs = await stored(session, "jobs", "subject_id", uuid.UUID(classification_id))
    await classify_image_job(ctx, str(jobs[-1]["id"]))
    session.expire_all()


async def fetch(
    client: AsyncClient, headers: dict[str, str], id: str
) -> dict[str, Any]:
    response = await client.get(f"/classifications/{id}", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_upload_rejects_a_wrong_type_and_a_large_size(
    client: AsyncClient, tenant: Tenant
) -> None:
    org, _, headers = tenant
    body = {"filename": "a.heic", "content_type": "image/heic", "size_bytes": 10}

    wrong_type = await client.post("/uploads", headers=headers, json=body)
    too_large = await client.post(
        "/uploads",
        headers=headers,
        json={**body, "content_type": "image/png", "size_bytes": MAX_UPLOAD_BYTES + 1},
    )
    ok = await client.post(
        "/uploads",
        headers=headers,
        json={**body, "content_type": "image/png", "size_bytes": MAX_UPLOAD_BYTES},
    )

    assert (wrong_type.status_code, too_large.status_code) == (400, 400)
    assert ok.status_code == 201
    out = ok.json()
    assert out["key"].startswith(f"incoming/{org}/")
    assert uuid.UUID(out["key"].rsplit("/", 1)[1])
    assert out["upload_url"] == (
        f"https://storage.test/put/{out['key']}?type=image/png&exp=600"
    )
    assert out["expires_in"] == 600


async def test_create_rejects_a_key_outside_the_callers_prefix(
    client: AsyncClient, tenant: Tenant
) -> None:
    org, _, headers = tenant
    foreign = f"incoming/{uuid.uuid4()}/{uuid.uuid4()}"
    thumb = f"thumbs/{org}/{uuid.uuid4()}.webp"

    for key in (foreign, thumb, f"x/incoming/{org}/{uuid.uuid4()}"):
        response = await client.post(
            "/classifications", headers=headers, json={"key": key, "filename": "a"}
        )
        assert response.status_code == 400, key


async def test_create_returns_202_queued_and_a_job_row(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    tenant: Tenant,
) -> None:
    org, user, headers = tenant

    out = await submit(client, headers, fake_storage, jpeg())

    assert out["status"] == "queued"
    assert out["review_status"] == "not_required"
    assert out["filename"] == "lunch.jpg"
    assert out["submitted_by_name"] == "writer"
    assert out["cost_usd"] == 0
    assert out["verdict"] is None and out["confidence"] is None
    assert out["thumbnail_url"] is None and out["duplicate_of"] is None
    assert out["error_code"] is None
    (row,) = await stored(db_session, "classifications", "id", uuid.UUID(out["id"]))
    assert (row["org_id"], row["submitted_by"]) == (org, user)
    assert row["original_key"].startswith(f"incoming/{org}/")
    (job,) = await stored(db_session, "jobs", "subject_id", uuid.UUID(out["id"]))
    assert (job["kind"], job["status"], job["org_id"]) == (
        "classify_image",
        "queued",
        org,
    )
    assert row["job_id"] == job["id"]


async def test_the_rate_limit_gives_429(
    client: AsyncClient, fake_storage: FakeStorage, tenant: Tenant
) -> None:
    _, _, headers = tenant
    # The test settings allow three per minute.
    for _ in range(3):
        await submit(client, headers, fake_storage, jpeg())
    upload = await client.post(
        "/uploads",
        headers=headers,
        json={"filename": "d.jpg", "content_type": "image/jpeg", "size_bytes": 1},
    )

    response = await client.post(
        "/classifications",
        headers=headers,
        json={"key": upload.json()["key"], "filename": "d.jpg"},
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


async def test_the_job_completes_the_row_with_the_fixture(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    org, user, headers = tenant
    data = jpeg()
    created = await submit(client, headers, fake_storage, data)

    await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert out["status"] == "completed"
    assert out["review_status"] == "not_required"
    assert out["verdict"] == "hot_dog"
    assert out["confidence"] == 0.97
    assert "sausage" in out["observations"]
    assert out["latency_ms"] >= 0
    assert out["cost_usd"] == 0.0038
    assert out["duplicate_of"] is None and out["error_code"] is None
    thumb_key = f"thumbs/{org}/{created['id']}.webp"
    assert out["thumbnail_url"] == f"https://storage.test/get/{thumb_key}?exp=3600"
    thumb, content_type = fake_storage.objects[thumb_key]
    assert content_type == "image/webp" and thumb[8:12] == b"WEBP"
    (row,) = await stored(db_session, "classifications", "id", uuid.UUID(out["id"]))
    assert (row["original_mime"], row["original_bytes"]) == ("image/jpeg", len(data))
    assert len(row["image_sha256"]) == 64
    (call,) = await stored(db_session, "llm_calls", "subject_id", uuid.UUID(out["id"]))
    assert row["llm_call_id"] == call["id"] and call["user_id"] == user
    (job,) = await stored(db_session, "jobs", "subject_id", uuid.UUID(out["id"]))
    assert job["status"] == "succeeded"
    assert job["result"] == {"outcome": "classified", "verdict": "hot_dog"}
    assert row["updated_at"] > row["created_at"]


async def test_low_confidence_goes_to_review(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    worker_ctx["llm_provider"].fixture = "hotdog_low"
    created = await submit(client, headers, fake_storage, jpeg())

    await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["review_status"]) == ("completed", "pending")
    assert (out["verdict"], out["confidence"]) == ("not_hot_dog", 0.62)


async def test_a_duplicate_copies_the_verdict_without_a_call(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    provider: FakeProvider = worker_ctx["llm_provider"]
    data = jpeg()
    first = await submit(client, headers, fake_storage, data, "one.jpg")
    await run(worker_ctx, db_session, first["id"])
    second = await submit(client, headers, fake_storage, data, "two.jpg")

    await run(worker_ctx, db_session, second["id"])

    original = await fetch(client, headers, first["id"])
    copy = await fetch(client, headers, second["id"])
    assert copy["status"] == "completed"
    assert copy["duplicate_of"] == first["id"]
    assert copy["cost_usd"] == 0
    assert (copy["verdict"], copy["confidence"]) == ("hot_dog", 0.97)
    assert copy["observations"] == original["observations"]
    assert copy["review_status"] == original["review_status"]
    assert copy["thumbnail_url"] == original["thumbnail_url"]
    assert len(provider.requests) == 1
    assert (
        await stored(db_session, "llm_calls", "subject_id", uuid.UUID(copy["id"])) == []
    )
    # The copy is never the original of a third upload.
    third = await submit(client, headers, fake_storage, data, "three.jpg")
    await run(worker_ctx, db_session, third["id"])
    assert (await fetch(client, headers, third["id"]))["duplicate_of"] == first["id"]


async def test_a_payload_that_is_not_an_image_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    created = await submit(client, headers, fake_storage, b"%PDF-1.4 not an image")

    await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "invalid_image")
    assert out["verdict"] is None and out["thumbnail_url"] is None
    assert worker_ctx["llm_provider"].requests == []
    (job,) = await stored(db_session, "jobs", "subject_id", uuid.UUID(out["id"]))
    assert job["status"] == "succeeded"


async def test_a_missing_object_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    created = await submit(client, headers, fake_storage, None)

    await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "missing_object")


async def test_an_object_over_the_cap_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    created = await submit(client, headers, fake_storage, b"x" * (MAX_UPLOAD_BYTES + 1))

    await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "too_large")


async def test_a_provider_error_retries_then_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    worker_ctx["llm_provider"].fixture = "refusal"
    created = await submit(client, headers, fake_storage, jpeg())
    row_id = uuid.UUID(created["id"])

    with pytest.raises(Retry):
        await run(worker_ctx, db_session, created["id"])

    assert (await fetch(client, headers, created["id"]))["status"] == "processing"
    (job,) = await stored(db_session, "jobs", "subject_id", row_id)
    assert (job["status"], job["attempts"]) == ("queued", 1)
    # The next run is the last attempt.
    await db_session.execute(
        text("UPDATE jobs SET max_attempts = 2 WHERE id = :id"), {"id": job["id"]}
    )
    await db_session.commit()

    with pytest.raises(LLMCallError):
        await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "provider_error")
    (job,) = await stored(db_session, "jobs", "subject_id", row_id)
    assert (job["status"], job["attempts"]) == ("failed", 2)


async def test_a_second_job_on_a_classified_row_makes_no_call(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    org, _, headers = tenant
    provider: FakeProvider = worker_ctx["llm_provider"]
    created = await submit(client, headers, fake_storage, jpeg())
    await run(worker_ctx, db_session, created["id"])
    row_id = uuid.UUID(created["id"])
    again = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO jobs (id, org_id, kind, subject_id, idempotency_key, status, "
            "attempts, max_attempts, request_id, created_at) VALUES (:id, :org, "
            "'classify_image', :subject, :key, 'queued', 0, 3, 'req', now())"
        ),
        {
            "id": again,
            "org": org,
            "subject": row_id,
            "key": f"classify_image:{row_id}:{again}",
        },
    )
    await db_session.commit()

    await classify_image_job(worker_ctx, str(again))

    assert len(provider.requests) == 1
    jobs = await stored(db_session, "jobs", "subject_id", row_id)
    outcomes = {job["id"]: job["result"]["outcome"] for job in jobs}
    assert outcomes[again] == "already_classified"
    assert sorted(outcomes.values()) == ["already_classified", "classified"]
    assert (await fetch(client, headers, created["id"]))["status"] == "completed"


async def test_list_filters_newest_first_with_thumbnails(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    provider: FakeProvider = worker_ctx["llm_provider"]
    sure = await submit(client, headers, fake_storage, jpeg((10, 20, 30)), "sure.jpg")
    await run(worker_ctx, db_session, sure["id"])
    provider.fixture = "hotdog_low"
    unsure = await submit(
        client, headers, fake_storage, jpeg((40, 50, 60)), "unsure.jpg"
    )
    await run(worker_ctx, db_session, unsure["id"])
    waiting = await submit(
        client, headers, fake_storage, jpeg((70, 80, 90)), "wait.jpg"
    )

    everything = await client.get("/classifications", headers=headers)

    assert everything.status_code == 200
    body = everything.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [
        waiting["id"],
        unsure["id"],
        sure["id"],
    ]
    assert [item["thumbnail_url"] is not None for item in body["items"]] == [
        False,
        True,
        True,
    ]

    async def ids(query: str) -> tuple[list[str], int]:
        response = await client.get(f"/classifications?{query}", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        return [item["id"] for item in data["items"]], data["total"]

    assert await ids("status=completed") == ([unsure["id"], sure["id"]], 2)
    assert await ids("status=queued") == ([waiting["id"]], 1)
    assert await ids("review_status=pending") == ([unsure["id"]], 1)
    assert await ids("verdict=hot_dog") == ([sure["id"]], 1)
    assert await ids("verdict=not_hot_dog&status=completed") == ([unsure["id"]], 1)
    assert await ids("limit=1") == ([waiting["id"]], 3)
    for bad in ("limit=0", "limit=201", "status=done"):
        response = await client.get(f"/classifications?{bad}", headers=headers)
        assert response.status_code == 422, bad


async def insert_job(
    session: AsyncSession, org: uuid.UUID, subject: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """A queued job row of the classification kind. Returns id and arq job id."""
    job_id = uuid.uuid4()
    key = f"{JOB_KIND}:{subject}:{job_id}"
    await session.execute(
        text(
            "INSERT INTO jobs (id, org_id, kind, subject_id, idempotency_key, status, "
            "attempts, max_attempts, request_id, created_at) VALUES (:id, :org, "
            ":kind, :subject, :key, 'queued', 0, 3, 'req', now())"
        ),
        {"id": job_id, "org": org, "kind": JOB_KIND, "subject": subject, "key": key},
    )
    return job_id, key


async def test_the_worker_runs_the_job_under_its_kind(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    arq_pool: ArqRedis,
    settings: Settings,
    tenant: Tenant,
) -> None:
    """`start_job` enqueues by kind. The registered function must carry it."""
    org, user, headers = tenant
    row_id = await insert_classification(db_session, org, user)
    fake_storage.objects[f"incoming/{org}/{row_id}"] = (jpeg(), "image/jpeg")
    _, key = await insert_job(db_session, org, row_id)
    await db_session.commit()
    # Its own queue: the acceptance tests leave jobs on the run's queue.
    queue = f"{settings.WORKER_QUEUE_NAME}:classify"
    job_ids = await stored(db_session, "jobs", "subject_id", row_id)
    enqueued = await arq_pool.enqueue_job(
        JOB_KIND, str(job_ids[0]["id"]), _job_id=key, _queue_name=queue
    )
    assert enqueued is not None
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_pool=arq_pool,
        queue_name=queue,
        ctx=worker_ctx,
        burst=True,
        max_jobs=1,
        poll_delay=0.05,
        keep_result=0,
        handle_signals=False,
        max_tries=settings.WORKER_MAX_ATTEMPTS,
        job_timeout=settings.WORKER_JOB_TIMEOUT_SECONDS,
    )

    try:
        completed = await worker.run_check()
    finally:
        await arq_pool.delete(queue, queue + health_check_key_suffix)

    assert (completed, worker.jobs_failed) == (1, 0)
    db_session.expire_all()
    out = await fetch(client, headers, str(row_id))
    assert (out["status"], out["verdict"]) == ("completed", "hot_dog")


async def test_a_cancelled_job_fails_the_row_with_timeout(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    """arq cancels at job_timeout and does not run the job again."""
    _, _, headers = tenant
    provider: FakeProvider = worker_ctx["llm_provider"]

    def stream(request: Any) -> Any:
        raise asyncio.CancelledError

    provider.stream = stream  # pyright: ignore[reportAttributeAccessIssue]
    created = await submit(client, headers, fake_storage, jpeg())

    with pytest.raises(asyncio.CancelledError):
        await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "timeout")
    (job,) = await stored(db_session, "jobs", "subject_id", uuid.UUID(out["id"]))
    assert job["status"] == "failed"


async def test_a_storage_error_on_the_last_attempt_fails_the_row(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, _, headers = tenant
    created = await submit(client, headers, fake_storage, jpeg())
    row_id = uuid.UUID(created["id"])
    (job,) = await stored(db_session, "jobs", "subject_id", row_id)
    await db_session.execute(
        text("UPDATE jobs SET max_attempts = 1 WHERE id = :id"), {"id": job["id"]}
    )
    await db_session.commit()

    async def get_bytes(key: str) -> bytes:
        raise RuntimeError("storage down")

    fake_storage.get_bytes = get_bytes  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(RuntimeError, match="storage down"):
        await run(worker_ctx, db_session, created["id"])

    out = await fetch(client, headers, created["id"])
    assert (out["status"], out["error_code"]) == ("failed", "worker_error")
    (job,) = await stored(db_session, "jobs", "subject_id", row_id)
    assert (job["status"], job["attempts"]) == ("failed", 1)


async def test_a_reviewed_original_passes_its_decision_to_the_copy(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
) -> None:
    _, user, headers = tenant
    data = jpeg()
    first = await submit(client, headers, fake_storage, data, "one.jpg")
    await run(worker_ctx, db_session, first["id"])
    await db_session.execute(
        text(
            "UPDATE classifications SET review_status = 'reviewed', "
            "final_verdict = 'not_hot_dog', reviewed_by = :user, reviewed_at = now() "
            "WHERE id = :id"
        ),
        {"user": user, "id": uuid.UUID(first["id"])},
    )
    await db_session.commit()
    second = await submit(client, headers, fake_storage, data, "two.jpg")

    await run(worker_ctx, db_session, second["id"])

    copy = await fetch(client, headers, second["id"])
    assert copy["duplicate_of"] == first["id"]
    assert (copy["review_status"], copy["final_verdict"]) == ("reviewed", "not_hot_dog")
    assert copy["reviewed_at"] is not None
    (row,) = await stored(db_session, "classifications", "id", uuid.UUID(copy["id"]))
    assert row["reviewed_by"] == user


async def test_a_job_on_an_image_in_flight_waits_and_copies_the_owner(
    client: AsyncClient,
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    worker_ctx: dict[str, Any],
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two uploads of one image at once: the second copies the first, no call."""
    org, user, headers = tenant
    provider: FakeProvider = worker_ctx["llm_provider"]
    data = jpeg()
    sha256 = hashlib.sha256(data).hexdigest()
    # The owner: another worker is classifying the same image right now.
    owner = await insert_classification(db_session, org, user)
    await db_session.execute(
        text(
            "UPDATE classifications SET status = 'processing', image_sha256 = :sha "
            "WHERE id = :id"
        ),
        {"sha": sha256, "id": owner},
    )
    await db_session.commit()
    created = await submit(client, headers, fake_storage, data)
    waits: list[int] = []

    async def owner_completes() -> None:
        """Runs in place of the poll pause: the owner finishes meanwhile.

        On the raw connection: a second session would nest a savepoint
        inside the job's open one.
        """
        waits.append(1)
        await db_connection.execute(
            text(
                "UPDATE classifications SET status = 'completed', verdict = 'hot_dog', "
                "confidence = 0.91, observations = 'A hot dog.', thumbnail_key = :t "
                "WHERE id = :id"
            ),
            {"t": f"thumbs/{org}/{owner}.webp", "id": owner},
        )

    monkeypatch.setattr(job_module, "_pause", owner_completes)

    await run(worker_ctx, db_session, created["id"])

    assert waits == [1]
    assert provider.requests == []
    copy = await fetch(client, headers, created["id"])
    assert copy["status"] == "completed"
    assert copy["duplicate_of"] == str(owner)
    assert (copy["verdict"], copy["confidence"], copy["cost_usd"]) == (
        "hot_dog",
        0.91,
        0,
    )
    assert (
        copy["thumbnail_url"]
        == f"https://storage.test/get/thumbs/{org}/{owner}.webp?exp=3600"
    )
    (row,) = await stored(db_session, "classifications", "id", uuid.UUID(copy["id"]))
    assert row["image_sha256"] == sha256
