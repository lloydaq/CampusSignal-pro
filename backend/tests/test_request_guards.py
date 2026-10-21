"""Origin check, body-size limits and client address resolution (AUTH-008, AUTH-007).

No database: the guards answer before any route code runs.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.request_guards import MAX_BODY_BYTES, client_address, normalize_origin
from tests.conftest import APP_ORIGIN

LOGIN = "/api/v1/auth/login"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:5173", ("http", "localhost", 5173)),
        ("http://LOCALHOST:5173", ("http", "localhost", 5173)),
        ("http://localhost:5173/", ("http", "localhost", 5173)),
        ("https://campussignal.example", ("https", "campussignal.example", 443)),
        ("https://campussignal.example:443", ("https", "campussignal.example", 443)),
        ("http://campussignal.example", ("http", "campussignal.example", 80)),
        ("null", None),
        ("", None),
        (None, None),
        ("localhost:5173", None),
        ("ftp://localhost:5173", None),
        ("http://localhost:5173/path", None),
        ("http://localhost:5173?x=1", None),
        ("http://user@localhost:5173", None),
        ("http://localhost:notaport", None),
    ],
)
def test_normalize_origin(value: str | None, expected: tuple[str, str, int] | None) -> None:
    assert normalize_origin(value) == expected


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "http://localhost:5174",  # same host, different port
        "https://localhost:5173",  # same host and port, different scheme
        "http://localhost.evil.example:5173",
        "http://localhost:5173.evil.example",
        "",
    ],
)
def test_write_with_wrong_origin_is_refused(bare_client: TestClient, origin: str) -> None:
    response = bare_client.post(LOGIN, json={}, headers={"Origin": origin})
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "origin_not_allowed"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_unsafe_method_needs_the_origin(bare_client: TestClient, method: str) -> None:
    response = bare_client.request(method, "/healthz")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_missing_origin_is_refused_before_the_body_is_looked_at(bare_client: TestClient) -> None:
    # An invalid body would be a 422 if validation ran first.
    response = bare_client.post(
        LOGIN, content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 403


def test_correct_origin_reaches_routing(bare_client: TestClient) -> None:
    # POST /healthz doesn't exist, so a request that passes the guard is a 405 from routing.
    assert bare_client.post("/healthz", headers={"Origin": APP_ORIGIN}).status_code == 405


@pytest.mark.parametrize("path", ["/healthz", "/api/v1/openapi.json"])
def test_reads_never_need_an_origin(bare_client: TestClient, path: str) -> None:
    assert bare_client.get(path).status_code == 200


def test_oversized_body_is_refused_by_declared_length(client: TestClient) -> None:
    response = client.post(LOGIN, content=b"x" * (MAX_BODY_BYTES + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_chunked_body_is_refused(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"email": '
        yield b'"a@b.example"}'

    response = client.post(LOGIN, content=chunks())
    assert response.status_code == 411
    assert response.json()["error"]["code"] == "length_required"


def test_body_at_the_limit_is_allowed_through_the_guard(client: TestClient) -> None:
    # Too large for the schema (not JSON), but past the size guard: a 4xx from the app, not 413.
    response = client.post("/healthz", content=b"x" * MAX_BODY_BYTES)
    assert response.status_code == 405


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 5000) if peer is not None else None,
    }
    return Request(scope)


def test_forwarded_header_is_ignored_without_trusted_proxies() -> None:
    assert client_address(_request("198.51.100.7", "203.0.113.9"), 0) == "198.51.100.7"


def test_one_proxy_uses_the_rightmost_hop() -> None:
    request = _request("10.0.0.1", "6.6.6.6, 203.0.113.9")
    assert client_address(request, 1) == "203.0.113.9"


def test_two_proxies_use_the_second_from_the_right() -> None:
    request = _request("10.0.0.1", "6.6.6.6, 203.0.113.9, 10.0.0.2")
    assert client_address(request, 2) == "203.0.113.9"


def test_client_supplied_hops_to_the_left_cannot_choose_the_address() -> None:
    a = client_address(_request("10.0.0.1", "1.1.1.1, 203.0.113.9"), 1)
    b = client_address(_request("10.0.0.1", "2.2.2.2, 203.0.113.9"), 1)
    assert a == b == "203.0.113.9"


@pytest.mark.parametrize("forwarded", [None, "", "not-an-ip", "   ,  "])
def test_missing_or_malformed_forwarding_falls_back_to_the_peer(forwarded: str | None) -> None:
    assert client_address(_request("198.51.100.7", forwarded), 1) == "198.51.100.7"


def test_too_few_hops_falls_back_to_the_peer() -> None:
    assert client_address(_request("198.51.100.7", "203.0.113.9"), 2) == "198.51.100.7"


def test_ipv6_clients_share_a_64() -> None:
    a = client_address(_request("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), 0)
    b = client_address(_request("2001:db8:1:2:1:2:3:4"), 0)
    assert a == b == "2001:db8:1:2::/64"
    assert client_address(_request("2001:db8:1:3::1"), 0) != a


def test_ipv4_mapped_ipv6_is_the_ipv4_address() -> None:
    assert client_address(_request("::ffff:198.51.100.7"), 0) == "198.51.100.7"


def test_non_ip_peer_is_a_stable_opaque_key() -> None:
    assert client_address(_request("testclient"), 0) == "testclient"
    assert client_address(_request(None), 0) == "unknown"
