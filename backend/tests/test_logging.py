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


def _logged_exception(exc: BaseException) -> dict[str, object]:
    try:
        raise exc
    except BaseException:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    result: dict[str, object] = json.loads(JsonFormatter().format(record))
    return result


def test_exception_messages_never_reach_the_log() -> None:
    """Rules R-2.11 (Phase 9a): a database error's text can quote the failing values (an
    email, a roll number, a score). The log keeps the type and the stack, not the message,
    for the exception and everything chained to it."""

    class UniqueViolation(Exception):
        pass

    # The values arrive at runtime (the stack quotes source lines, never values).
    inner_text = "roll_number N-001 for aarav@northfield.example"
    outer_text = 'duplicate key (email)=(aarav@northfield.example) [parameters: {"score": 18.5}]'
    try:
        try:
            raise ValueError(inner_text)
        except ValueError as inner:
            raise UniqueViolation(outer_text) from inner
    except UniqueViolation as outer:
        payload = _logged_exception(outer)
    text = str(payload["exc_info"])
    for secret in ("aarav@northfield.example", "N-001", "18.5", "duplicate key"):
        assert secret not in text, secret
    assert "UniqueViolation" in text and "ValueError" in text
    assert "test_exception_messages_never_reach_the_log" in text  # the stack is still there
