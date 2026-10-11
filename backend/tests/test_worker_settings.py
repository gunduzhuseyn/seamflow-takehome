"""The worker registers at least one function, so arq starts."""

import logging

import pytest

from app.classifications.models import JOB_KIND
from app.jobs.heartbeat import heartbeat
from app.worker import WorkerSettings


def test_worker_registers_at_least_one_function() -> None:
    assert WorkerSettings.functions
    assert heartbeat in WorkerSettings.functions


def test_worker_registers_the_classify_job_under_its_kind() -> None:
    names = {getattr(f, "name", None) for f in WorkerSettings.functions}
    assert JOB_KIND in names


async def test_heartbeat_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.jobs"):
        await heartbeat({})

    assert [record.getMessage() for record in caplog.records] == ["heartbeat"]
