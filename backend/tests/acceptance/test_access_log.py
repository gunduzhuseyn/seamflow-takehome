import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.fakes import FakeClerk, TokenFactory


def access_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.access"]


async def test_me_logs_one_access_record(
    client: AsyncClient,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_clerk.emails["user_log"] = "log@example.com"
    headers = {
        "Authorization": f"Bearer {make_token('user_log')}",
        "X-Request-Id": "req-access-1",
    }

    with caplog.at_level(logging.INFO):
        response = await client.get("/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    [record] = access_records(caplog)
    assert record.levelno == logging.INFO
    assert vars(record)["request_id"] == "req-access-1"
    assert vars(record)["method"] == "GET"
    assert vars(record)["path"] == "/me"
    assert vars(record)["status"] == 200
    assert vars(record)["user_id"] == body["user"]["id"]
    assert vars(record)["org_id"] == body["org"]["id"]
    assert isinstance(vars(record)["duration_ms"], float)


async def test_exception_logs_error_and_keeps_request_id(
    app: FastAPI, client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom() -> None:
        raise RuntimeError("forced")

    app.add_api_route("/boom", boom)

    with caplog.at_level(logging.INFO):
        response = await client.get("/boom", headers={"X-Request-Id": "req-boom-1"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "req-boom-1"
    [record] = access_records(caplog)
    assert record.levelno == logging.ERROR
    assert vars(record)["request_id"] == "req-boom-1"
    assert vars(record)["status"] == 500
    assert record.exc_info is not None
