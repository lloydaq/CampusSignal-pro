"""Operator CLI and Jobs CLI without a database: argument handling, prompts, failure paths."""

import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.cli import main as cli
from app.jobs import main as jobs
from app.services import retention
from tests.conftest import make_settings

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
GOOD_PASSWORD = "tidal-quartz-lantern"
ARGS = ["create-platform-admin", "--email", "ops@campussignal.example", "--display-name", "Ops"]


def _passwords(*answers: str) -> Callable[[str], str]:
    queue = list(answers)

    def read(prompt: str) -> str:
        return queue.pop(0)

    return read


def _unusable_factory() -> Session:
    raise AssertionError("the database must not be touched")


def _run(
    argv: list[str], read: Callable[[str], str], factory: Any = _unusable_factory
) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(argv, session_factory=factory, read_password=read, now=NOW, out=out)
    return code, out.getvalue()


@pytest.mark.parametrize("argv", [[], ["create-platform-admin"], ["unknown-command"]])
def test_cli_rejects_missing_or_unknown_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(argv)
    assert exc.value.code == 2


def test_cli_has_no_password_argument() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([*ARGS, "--password", GOOD_PASSWORD])


@pytest.mark.parametrize(
    ("field", "value"), [("--email", "not-an-email"), ("--display-name", "   ")]
)
def test_invalid_identity_fails_before_asking_for_a_password(field: str, value: str) -> None:
    argv = list(ARGS)
    argv[argv.index(field) + 1] = value

    def never(prompt: str) -> str:
        raise AssertionError("must not prompt")

    code, output = _run(argv, never)
    assert code == cli.EXIT_FAILED
    assert "Nothing was created" in output


def test_mismatched_passwords_create_nothing() -> None:
    code, output = _run(ARGS, _passwords(GOOD_PASSWORD, GOOD_PASSWORD + "x"))
    assert code == cli.EXIT_FAILED
    assert "do not match" in output
    assert GOOD_PASSWORD not in output


def test_weak_password_is_refused_without_echoing_it() -> None:
    factory = MagicMock()
    code, output = _run(ARGS, _passwords("password", "password"), factory)
    assert code == cli.EXIT_FAILED
    assert output.startswith("password: ")
    assert "'password'" not in output and '"password"' not in output
    factory.return_value.__enter__.return_value.add.assert_not_called()


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_cancelled_prompt_creates_nothing(error: type[BaseException]) -> None:
    def read(prompt: str) -> str:
        raise error

    code, output = _run(ARGS, read)
    assert code == cli.EXIT_FAILED
    assert "Cancelled" in output


def test_jobs_cli_accepts_only_run_due() -> None:
    assert jobs.build_parser().parse_args(["run-due"]).command == "run-due"
    for argv in ([], ["purge-everything"]):
        with pytest.raises(SystemExit):
            jobs.build_parser().parse_args(argv)


def test_a_failing_purge_is_reported_and_the_others_still_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ran: list[str] = []

    def ok(db: Session, settings: object, now: datetime) -> int:
        ran.append("ok")
        return 3

    def broken(db: Session, settings: object, now: datetime) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(retention, "PURGES", {"first": broken, "second": ok})
    sessions: list[MagicMock] = []

    def factory() -> MagicMock:
        session = MagicMock()
        session.__enter__.return_value = session
        sessions.append(session)
        return session

    with caplog.at_level(logging.INFO, logger="app.jobs"):
        code = jobs.run_due(make_settings(), factory, NOW)

    assert code == jobs.EXIT_FAILED
    assert ran == ["ok"]
    assert sessions[0].rollback.called and not sessions[0].commit.called
    assert sessions[1].commit.called
    records = {r.getMessage(): r.__dict__ for r in caplog.records}
    assert records["retention_purge_failed"]["purge"] == "first"
    assert records["retention_purge_failed"]["error_type"] == "RuntimeError"
    assert records["retention_purge"]["purge"] == "second"
    assert records["retention_purge"]["deleted"] == 3
