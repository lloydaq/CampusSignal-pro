"""Route inventory (Rules R-2.1, PRD §17.1): every operation is either on the explicit public
allowlist or requires a signed-in session, and every state-changing route sits behind the
Origin check. A new route that is neither fails here, so protection can't be forgotten.

The inventory reads the OpenAPI schema (public behaviour), where `current_session` shows up
as the `SessionCookie` security scheme, and the enforcement tests then check that each
protected operation really answers 401 without a session.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Security
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import (
    SESSION_SCHEME_NAME,
    Campus,
    campus_context,
    current_session,
    platform_admin,
)
from app.main import create_app
from tests.conftest import make_settings
from tests.tenant_isolation_cases import CASES

# Operations that may be called without signing in. Adding to this set is a security
# decision: say why in the review.
PUBLIC: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/healthz"),  # liveness, no data
        ("GET", "/readyz"),  # readiness, only ready / not_ready
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/verify-email"),  # authorised by the emailed single-use token
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/csrf"),  # the caller's own session's token, or null
        ("POST", "/api/v1/auth/password-reset/request"),
        ("POST", "/api/v1/auth/password-reset/confirm"),  # authorised by the emailed token
    }
)
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})

Operation = dict[str, Any]


def operations(app: FastAPI) -> dict[tuple[str, str], Operation]:
    schema = app.openapi()
    return {
        (method.upper(), path): op
        for path, item in schema["paths"].items()
        for method, op in item.items()
    }


def is_protected(op: Operation) -> bool:
    return any(SESSION_SCHEME_NAME in requirement for requirement in op.get("security", []))


def unprotected(app: FastAPI, public: frozenset[tuple[str, str]]) -> list[str]:
    return sorted(
        f"{method} {path}"
        for (method, path), op in operations(app).items()
        if (method, path) not in public and not is_protected(op)
    )


def api_routes(app: FastAPI) -> Iterator[tuple[str, APIRoute]]:
    """Every APIRoute with its full path, including routes inside included routers (whose own
    `path` lacks the prefix they were included under)."""
    pending: list[tuple[str, Any]] = [("", route) for route in app.routes]
    while pending:
        prefix, route = pending.pop()
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        router = getattr(route, "original_router", None)
        if router is not None:
            context = getattr(route, "include_context", None)
            inner = prefix + (getattr(context, "prefix", "") or "")
            pending.extend((inner, child) for child in router.routes)


@pytest.fixture(scope="module")
def real_app() -> FastAPI:
    return create_app(make_settings())


def test_every_operation_is_public_by_allowlist_or_requires_a_session(real_app: FastAPI) -> None:
    assert unprotected(real_app, PUBLIC) == []


def test_the_inventory_sees_every_route(real_app: FastAPI) -> None:
    # A route hidden from the schema would escape the check above.
    routes = [route for _, route in api_routes(real_app)]
    assert routes, "route discovery found nothing"
    assert all(route.include_in_schema for route in routes)
    # The full paths found here must be exactly the documented ones.
    assert {path for path, _ in api_routes(real_app)} == {p for _, p in operations(real_app)}
    methods = sum(len((route.methods or set()) - {"HEAD", "OPTIONS"}) for route in routes)
    assert methods == len(operations(real_app))


def test_the_allowlist_has_no_stale_entries(real_app: FastAPI) -> None:
    assert set(operations(real_app)) >= PUBLIC


def test_the_inventory_detects_an_unprotected_route() -> None:
    app = create_app(make_settings())

    @app.get("/api/v1/oops")
    def oops() -> dict[str, str]:  # looks protected, nobody protected it
        return {"secret": "data"}

    @app.post("/api/v1/guarded")
    def guarded(_: Any = Security(current_session)) -> dict[str, str]:  # noqa: B008
        return {}

    assert unprotected(app, PUBLIC) == ["GET /api/v1/oops"]


CAMPUS_PREFIX = "/api/v1/campus"


def _calls(dependant: Any) -> Iterator[Any]:
    for sub in dependant.dependencies:
        yield sub.call
        yield from _calls(sub)


def campus_routes_without_context(app: FastAPI) -> list[str]:
    """Campus routes must take their college from `campus_context` (TENANT-001)."""
    return sorted(
        f"{sorted(route.methods or [])} {path}"
        for path, route in api_routes(app)
        if path.startswith(CAMPUS_PREFIX) and campus_context not in _calls(route.dependant)
    )


def test_every_campus_route_uses_the_campus_context(real_app: FastAPI) -> None:
    assert campus_routes_without_context(real_app) == []


def test_the_campus_check_detects_a_route_without_the_context() -> None:
    app = create_app(make_settings())

    @app.get(f"{CAMPUS_PREFIX}/oops")
    def oops(_: Any = Security(current_session)) -> dict[str, str]:  # noqa: B008
        return {}  # signed in, but no college context: it could read any college

    @app.get(f"{CAMPUS_PREFIX}/fine")
    def fine(_: Campus) -> dict[str, str]:
        return {}

    nested = APIRouter(prefix="/campus")

    @nested.get("/nested-oops")
    def nested_oops(_: Any = Security(current_session)) -> dict[str, str]:  # noqa: B008
        return {}

    app.include_router(nested, prefix="/api/v1")
    assert campus_routes_without_context(app) == [
        f"['GET'] {CAMPUS_PREFIX}/nested-oops",
        f"['GET'] {CAMPUS_PREFIX}/oops",
    ]


PLATFORM_PREFIX = "/api/v1/platform"


def platform_routes_without_admin_check(app: FastAPI) -> list[str]:
    """Platform routes must go through `platform_admin` (404 for everyone else)."""
    return sorted(
        f"{sorted(route.methods or [])} {path}"
        for path, route in api_routes(app)
        if path.startswith(PLATFORM_PREFIX) and platform_admin not in _calls(route.dependant)
    )


def test_every_platform_route_requires_a_platform_admin(real_app: FastAPI) -> None:
    assert platform_routes_without_admin_check(real_app) == []
    assert any(path.startswith(PLATFORM_PREFIX) for path, _ in api_routes(real_app))


def test_the_platform_check_detects_a_route_without_it() -> None:
    app = create_app(make_settings())

    @app.get(f"{PLATFORM_PREFIX}/oops")
    def oops(_: Any = Security(current_session)) -> dict[str, str]:  # noqa: B008
        return {}  # any signed-in user could call it

    assert platform_routes_without_admin_check(app) == [f"['GET'] {PLATFORM_PREFIX}/oops"]


def test_every_campus_operation_is_in_the_tenant_isolation_suite(real_app: FastAPI) -> None:
    campus = {(m, p) for (m, p) in operations(real_app) if p.startswith(CAMPUS_PREFIX)}
    assert campus == set(CASES), "add the new campus route to tests/tenant_isolation_cases.py"


def test_the_protected_operations_are_the_ones_we_expect(real_app: FastAPI) -> None:
    protected = {f"{m} {p}" for (m, p), op in operations(real_app).items() if is_protected(op)}
    assert protected == {
        "GET /api/v1/me",
        "POST /api/v1/me/password",
        "POST /api/v1/auth/logout",
        "POST /api/v1/auth/logout-all",
        "POST /api/v1/auth/resend-verification",
        "POST /api/v1/invites/accept",
        "GET /api/v1/platform/colleges",
        "POST /api/v1/platform/colleges",
        "GET /api/v1/platform/colleges/{college_id}",
        "PATCH /api/v1/platform/colleges/{college_id}",
        "POST /api/v1/platform/colleges/{college_id}/admin-invites",
        "GET /api/v1/platform/users",
        "POST /api/v1/platform/users/{user_id}/suspend",
        "POST /api/v1/platform/users/{user_id}/unsuspend",
        "GET /api/v1/platform/audit-log",
        "GET /api/v1/campus/departments",
        "POST /api/v1/campus/departments",
        "GET /api/v1/campus/departments/{department_id}",
        "PATCH /api/v1/campus/departments/{department_id}",
        "POST /api/v1/campus/roster/import",
        "GET /api/v1/campus/roster",
        "POST /api/v1/campus/invites",
        "GET /api/v1/campus/invites",
        "GET /api/v1/campus/members",
        "PATCH /api/v1/campus/members/{membership_id}",
        "POST /api/v1/campus/members/{membership_id}/grants",
        "DELETE /api/v1/campus/members/{membership_id}/grants/{grant_id}",
        "GET /api/v1/campus/audit-log",
        "GET /api/v1/campus/notices",
        "POST /api/v1/campus/notices",
        "GET /api/v1/campus/notices/{notice_id}",
        "PATCH /api/v1/campus/notices/{notice_id}",
        "POST /api/v1/campus/notices/{notice_id}/publish",
        "POST /api/v1/campus/notices/{notice_id}/withdraw",
        "GET /api/v1/campus/membership-requests",
        "POST /api/v1/campus/membership-requests/{request_id}/approve",
        "POST /api/v1/campus/membership-requests/{request_id}/reject",
        "GET /api/v1/colleges",
        "POST /api/v1/me/membership-requests",
        "GET /api/v1/me/membership-requests",
    }


PROTECTED = sorted(
    (method, path)
    for (method, path), op in operations(create_app(make_settings())).items()
    if is_protected(op)
)
UNSAFE_OPERATIONS = sorted(
    (method, path) for (method, path) in operations(create_app(make_settings())) if method in UNSAFE
)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_operations_answer_401_without_a_session(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(("method", "path"), UNSAFE_OPERATIONS)
def test_every_state_changing_operation_refuses_requests_without_an_origin(
    bare_client: TestClient, method: str, path: str
) -> None:
    response = bare_client.request(method, path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"
