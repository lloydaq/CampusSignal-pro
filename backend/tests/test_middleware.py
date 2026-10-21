import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.middleware import SECURITY_HEADERS


def test_request_id_header_is_set_and_unique(client: TestClient) -> None:
    first = client.get("/healthz").headers["X-Request-ID"]
    second = client.get("/healthz").headers["X-Request-ID"]
    assert len(first) == 32
    assert first != second


def test_client_supplied_request_id_is_ignored(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "injected\nvalue"})
    assert response.headers["X-Request-ID"] != "injected\nvalue"


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/healthz")
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_access_log_uses_route_template_without_query(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        response = client.get("/healthz?token=abc123")
    records = [r for r in caplog.records if r.name == "app.access"]
    assert len(records) == 1
    record = records[0]
    assert record.__dict__["route"] == "/healthz"
    assert record.__dict__["status"] == 200
    assert "abc123" not in json.dumps({k: str(v) for k, v in record.__dict__.items()})
    assert response.status_code == 200


def test_access_log_for_unmatched_route(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/nope/123")
    record = next(r for r in caplog.records if r.name == "app.access")
    assert record.__dict__["route"] == "<unmatched>"
    assert record.__dict__["status"] == 404
