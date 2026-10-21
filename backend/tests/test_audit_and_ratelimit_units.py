"""Pure parts of the audit writer and rate limiter. Database behaviour is in tests/integration."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.ratelimit import Limit, _state, _window_start, hashed_key
from app.services.audit import _check_metadata

LIMIT = Limit(name="login:email", max_hits=5, window=timedelta(minutes=15))


def test_window_start_aligns_to_window_boundaries() -> None:
    now = datetime(2026, 10, 21, 10, 7, 30, tzinfo=UTC)
    assert _window_start(LIMIT, now) == datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    assert _window_start(LIMIT, now + timedelta(minutes=8)) == datetime(
        2026, 10, 21, 10, 15, tzinfo=UTC
    )


def test_state_reports_exceeded_and_retry_after() -> None:
    start = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    now = start + timedelta(minutes=10, seconds=30)
    assert not _state(LIMIT, 4, start, now).exceeded
    state = _state(LIMIT, 5, start, now)
    assert state.exceeded
    assert state.retry_after_seconds == 270


def test_hashed_key_hides_personal_values() -> None:
    key = hashed_key("aarav@northfield.example")
    assert "aarav" not in key
    assert len(key) == 64
    assert key == hashed_key("aarav@northfield.example")


@pytest.mark.parametrize(
    "metadata",
    [
        {"password": "x"},
        {"new_email": "a@b.example"},
        {"details": {"session_id": "abc"}},
        {"changes": [{"score": 9}]},
        {"token_hash": "00"},
    ],
)
def test_audit_metadata_refuses_sensitive_keys(metadata: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="must not contain sensitive key"):
        _check_metadata(metadata)


def test_audit_metadata_allows_identifiers_and_reasons() -> None:
    _check_metadata({"via": "cli", "attempts": 6, "ip_prefix": "203.0.113.0/24"})
