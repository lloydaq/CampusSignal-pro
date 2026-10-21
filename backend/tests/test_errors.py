"""Error envelope (architecture.md §12) for every error path."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import Conflict, Forbidden, NotAuthenticated, NotFound, RateLimited


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=5)
    password: str


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """Adds test-only routes exercising each error path."""

    @app.get("/_test/not-found")
    def _not_found() -> None:
        raise NotFound()

    @app.get("/_test/forbidden")
    def _forbidden() -> None:
        raise Forbidden()

    @app.get("/_test/unauthenticated")
    def _unauthenticated() -> None:
        raise NotAuthenticated()

    @app.get("/_test/conflict")
    def _conflict() -> None:
        raise Conflict("Changed by someone else.", code="version_conflict")

    @app.get("/_test/rate-limited")
    def _rate_limited() -> None:
        raise RateLimited(retry_after_seconds=30)

    @app.post("/_test/validate")
    def _validate(payload: _Payload) -> None:
        return None

    @app.get("/_test/boom")
    def _boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


def _envelope(body: Any) -> dict[str, Any]:
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    return error


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/_test/not-found", 404, "not_found"),
        ("/_test/forbidden", 403, "forbidden"),
        ("/_test/unauthenticated", 401, "not_authenticated"),
        ("/_test/conflict", 409, "version_conflict"),
        ("/_test/rate-limited", 429, "rate_limited"),
    ],
)
def test_app_errors_use_envelope(client: TestClient, path: str, status: int, code: str) -> None:
    response = client.get(path)
    assert response.status_code == status
    error = _envelope(response.json())
    assert error["code"] == code
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_rate_limited_sets_retry_after(client: TestClient) -> None:
    assert client.get("/_test/rate-limited").headers["Retry-After"] == "30"


def test_unknown_route_returns_not_found_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert _envelope(response.json())["code"] == "not_found"


def test_wrong_method_returns_envelope(client: TestClient) -> None:
    response = client.post("/healthz")
    assert response.status_code == 405
    assert _envelope(response.json())["code"] == "method_not_allowed"


def test_validation_error_lists_fields_without_echoing_input(client: TestClient) -> None:
    response = client.post(
        "/_test/validate",
        json={"title": "far too long", "password": "hunter2-secret", "college_id": "x"},
    )
    assert response.status_code == 422
    error = _envelope(response.json())
    assert error["code"] == "validation_error"
    fields = {d["field"] for d in error["details"]}
    assert fields == {"title", "college_id"}  # unknown field rejected (extra="forbid")
    assert "hunter2-secret" not in response.text
    assert "far too long" not in response.text


def test_unhandled_exception_returns_generic_500(client: TestClient) -> None:
    response = client.get("/_test/boom")
    assert response.status_code == 500
    error = _envelope(response.json())
    assert error["code"] == "internal_error"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"
