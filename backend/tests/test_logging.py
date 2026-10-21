import json
import logging

from app.core.logging import REDACTED, JsonFormatter, ScrubFilter, configure_logging, scrub
from app.core.request_context import request_id_var


def _record(msg: str = "event", args: object = None, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, msg, args, None)  # type: ignore[arg-type]
    record.__dict__.update(extra)
    return record


def test_scrub_filter_redacts_sensitive_extra_fields() -> None:
    record = _record(
        password="hunter2",
        session_id="abc",
        user_email="a@example.test",
        roll_number="NI-001",
        user_id="u-1",
    )
    ScrubFilter().filter(record)
    assert record.__dict__["password"] == REDACTED
    assert record.__dict__["session_id"] == REDACTED
    assert record.__dict__["user_email"] == REDACTED
    assert record.__dict__["roll_number"] == REDACTED
    assert record.__dict__["user_id"] == "u-1"


def test_scrub_filter_redacts_nested_values_and_dict_args() -> None:
    record = _record(
        "login %(user)s",
        args={"user": "u-1", "password": "x"},
        payload={"title": "ok", "auth": {"csrf_token": "t", "score": 99}},
    )
    ScrubFilter().filter(record)
    assert record.__dict__["payload"] == {
        "title": "ok",
        "auth": {"csrf_token": REDACTED, "score": REDACTED},
    }
    assert record.args == {"user": "u-1", "password": REDACTED}


def test_scrub_handles_lists() -> None:
    assert scrub([{"token": "t"}, "plain"]) == [{"token": REDACTED}, "plain"]


def test_json_formatter_includes_request_id_and_extras() -> None:
    token = request_id_var.set("req-123")
    try:
        record = _record("request", route="/healthz", status=200)
        ScrubFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-123"
    assert payload["message"] == "request"
    assert payload["route"] == "/healthz"
    assert payload["status"] == 200
    assert payload["level"] == "INFO"


def test_configure_logging_quiets_alembic_info() -> None:
    configure_logging("INFO")
    assert not logging.getLogger("alembic.runtime.migration").isEnabledFor(logging.INFO)
    assert logging.getLogger("alembic.runtime.migration").isEnabledFor(logging.WARNING)
