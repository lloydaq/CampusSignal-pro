"""`/readyz` and session handling without a database (unreachable loopback port)."""

import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import db
from tests.conftest import UNREACHABLE_DB_URL


def test_readyz_returns_503_when_database_unreachable(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.db"):
        response = client.get("/readyz")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "not_ready"
    assert error["details"] == {"database": "unreachable"}
    assert error["request_id"] == response.headers["X-Request-ID"]

    # Neither the response nor the logs reveal connection details.
    logged = json.dumps([{k: str(v) for k, v in r.__dict__.items()} for r in caplog.records])
    for secret_part in ("not-a-real-password", "127.0.0.1", UNREACHABLE_DB_URL):
        assert secret_part not in response.text
        assert secret_part not in logged
    record = next(r for r in caplog.records if r.getMessage() == "readiness_db_unreachable")
    assert record.__dict__["error_type"] == "OperationalError"


def test_readyz_returns_503_when_migrations_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "check_readiness", lambda *_: db.ReadinessProblem.MIGRATIONS_PENDING)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"migrations": "pending"}


def test_readyz_returns_200_when_ready(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "check_readiness", lambda *_: None)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_healthz_does_not_need_database(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_expected_migration_heads_read_from_scripts() -> None:
    assert db.expected_migration_heads() == frozenset({"0008"})


def test_get_session_yields_session_bound_to_app_engine_and_closes_it(app: FastAPI) -> None:
    seen: list[Session] = []

    @app.get("/_test/session")
    def _route(session: Session = Depends(db.get_session)) -> dict[str, bool]:  # noqa: B008
        seen.append(session)
        return {"bound": session.get_bind() is app.state.engine}

    with TestClient(app) as client:
        assert client.get("/_test/session").json() == {"bound": True}
    assert len(seen) == 1
    assert not seen[0].in_transaction()
