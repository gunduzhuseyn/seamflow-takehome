"""Log lines on stdout with the standard library. One record per line.

LOG_FORMAT=json writes one JSON object per line. LOG_FORMAT=text writes the
same fields as one readable line.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import LogFormat, LoggingSettings
from app.core.request_id import current_request_id

# LogRecord attributes that are not `extra` fields.
_BUILTIN = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
# Marks the handler that configure_logging installs, so a second call
# replaces it and keeps other handlers, for example the pytest capture.
HANDLER_NAME = "app"
# The HTTP clients log one line per request at INFO. The app logs one line
# per LLM call instead.
QUIET_LOGGERS = ("httpx", "httpx2", "httpcore", "httpcore2", "anthropic")


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    line: dict[str, Any] = {
        "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        "request_id": current_request_id(),
    }
    line.update({k: v for k, v in vars(record).items() if k not in _BUILTIN})
    return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = _fields(record)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


class TextFormatter(logging.Formatter):
    """`time LEVEL logger message key=value ...`. Empty values are left out."""

    def format(self, record: logging.LogRecord) -> str:
        line = _fields(record)
        head = [line.pop(k) for k in ("time", "level", "logger", "message")]
        pairs = [f"{k}={v}" for k, v in line.items() if v not in (None, "")]
        text = " ".join([*map(str, head), *pairs])
        if record.exc_info:
            text = f"{text}\n{self.formatException(record.exc_info)}"
        return text


def configure_logging(settings: LoggingSettings) -> None:
    """Route the root logger to one stdout handler. A second call replaces it."""
    formatter = (
        JsonFormatter() if settings.LOG_FORMAT is LogFormat.json else TextFormatter()
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    for old in [h for h in root.handlers if h.get_name() == HANDLER_NAME]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)
    # Uvicorn installs its own handlers. Its lines go to the root handler
    # instead. The access log middleware replaces uvicorn.access.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(logging.NOTSET)
    logging.getLogger("uvicorn.access").disabled = True
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
