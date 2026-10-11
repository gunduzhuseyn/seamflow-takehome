import json
import logging
import sys

from app.core.logging import JsonFormatter


def test_json_formatter_writes_one_parsable_line() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "app.access", logging.ERROR, __file__, 1, "request failed", None, exc_info
    )
    record.__dict__.update(
        request_id="req-1", method="GET", path="/me", status=500, duration_ms=1.5
    )

    line = JsonFormatter().format(record)

    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["level"] == "ERROR"
    assert parsed["logger"] == "app.access"
    assert parsed["message"] == "request failed"
    assert parsed["request_id"] == "req-1"
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/me"
    assert parsed["status"] == 500
    assert parsed["duration_ms"] == 1.5
    assert "ValueError: bad" in parsed["exception"]
    assert "time" in parsed
