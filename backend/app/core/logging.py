"""JSON logging with request IDs and a sensitive-field scrubber (architecture.md §16).

The scrubber is a backstop: code must not log sensitive values in the first place
(Rules R-2.11). It redacts structured fields passed via ``extra=`` and dict
arguments whose keys look sensitive; it cannot inspect free-form message text.
"""

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from app.core.request_context import current_request_id

REDACTED = "[REDACTED]"

# Matched as substrings of lower-cased keys.
SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "session",
    "cookie",
    "csrf",
    "authorization",
    "api_key",
    "email",
    "roll_number",
    "score",
    "attendance",
)

# Attributes every LogRecord has; anything else on a record came from ``extra=``.
# ``color_message`` is uvicorn's ANSI-coloured duplicate of the message.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
    | {"message", "asctime", "color_message"}
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if is_sensitive_key(str(k)) else scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key in _STANDARD_ATTRS:
                continue
            record.__dict__[key] = (
                REDACTED if is_sensitive_key(key) else scrub(record.__dict__[key])
            )
        if isinstance(record.args, dict):
            record.args = scrub(record.args)
        return True


def safe_exception_text(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None],
) -> str:
    """The stack of an exception and of everything chained to it, with every exception's
    message withheld (Rules R-2.11): a database error's text can quote the failing values,
    such as an email, a roll number or a score, which the scrubber can't see."""
    exc = exc_info[1]
    blocks: list[str] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        name = f"{type(exc).__module__}.{type(exc).__qualname__}"
        stack = "".join(traceback.format_tb(exc.__traceback__))
        blocks.append(f"Traceback (most recent call last):\n{stack}{name}: [message withheld]")
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return "\n\nThe above was raised while handling or caused by:\n\n".join(reversed(blocks))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": current_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = safe_exception_text(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ScrubFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Our middleware writes the access log (with request IDs, without query strings).
    logging.getLogger("uvicorn.access").disabled = True
    # /readyz inspects the migration version on every call; Alembic's INFO lines are noise.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
