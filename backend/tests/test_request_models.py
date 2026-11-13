"""Rules R-2.2 and R-2.7 as a standing check over every route (Phase 9a): each request body
forbids unknown fields (`extra="forbid"`, which OpenAPI shows as `additionalProperties: false`),
and no campus body can carry `college_id` (the college comes from the session's ACTIVE
membership, never from the client). Read from the OpenAPI schema, like the route inventory."""

from typing import Any

from app.main import create_app
from tests.conftest import make_settings

METHODS = {"post", "put", "patch", "delete"}


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = create_app(make_settings()).openapi()
    return schema


def _object_schemas(
    node: Any, components: dict[str, Any], seen: set[str]
) -> list[tuple[str, dict[str, Any]]]:
    """Every object schema reachable from `node`, by name (refs followed once)."""
    found: list[tuple[str, dict[str, Any]]] = []
    stack = [("(inline)", node)]
    while stack:
        name, current = stack.pop()
        if isinstance(current, dict):
            ref = current.get("$ref")
            if isinstance(ref, str):
                target = ref.rsplit("/", 1)[-1]
                if target not in seen:
                    seen.add(target)
                    stack.append((target, components[target]))
                continue
            if current.get("type") == "object" and "properties" in current:
                found.append((name, current))
            stack.extend((name, v) for v in current.values())
        elif isinstance(current, list):
            stack.extend((name, v) for v in current)
    return found


def _bodies() -> list[tuple[str, str, dict[str, Any]]]:
    schema = _schema()
    components = schema.get("components", {}).get("schemas", {})
    out = []
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in METHODS or "requestBody" not in operation:
                continue
            for name, body in _object_schemas(operation["requestBody"], components, set()):
                out.append((f"{method.upper()} {path}", name, body))
    return out


def test_there_are_request_bodies_to_check() -> None:
    assert len(_bodies()) > 40


def test_every_request_body_forbids_unknown_fields() -> None:
    lax = sorted(
        {
            f"{where}: {name}"
            for where, name, body in _bodies()
            if body.get("additionalProperties") is not False
        }
    )
    assert lax == []


def test_no_campus_body_names_a_college() -> None:
    carrying = sorted(
        {
            f"{where}: {name}"
            for where, name, body in _bodies()
            if "/campus" in where and "college_id" in body["properties"]
        }
    )
    assert carrying == []
