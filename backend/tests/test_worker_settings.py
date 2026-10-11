"""The worker registers at least one function, so arq starts."""

import logging

import pytest

from app.jobs.heartbeat import heartbeat
from app.worker import WorkerSettings


def test_worker_registers_at_least_one_function() -> None:
    assert WorkerSettings.functions
    assert heartbeat in WorkerSettings.functions


async def test_heartbeat_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.jobs"):
        await heartbeat({})

    assert [record.getMessage() for record in caplog.records] == ["heartbeat"]
