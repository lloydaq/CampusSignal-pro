"""Registry for the tenant-isolation suite (TENANT-005, PRD §17).

Every /api/v1/campus operation is listed here; `test_route_inventory` fails when one is
missing, so a new route can't skip the suite. The suite (tests/integration/
test_tenant_isolation.py) builds the two-college world, signs in as Northfield's college
admin (the widest campus permissions) and, per kind:

- OBJECT: calls the route on a Riverside object. Expect the same 404 as for an object that
  doesn't exist (TENANT-002) and no Riverside data in the body.
- LIST: calls the route while Riverside has matching data. Expect 200 and no Riverside data.
- CREATE: sends a body that names Riverside's college. Expect 422 (unknown field): the acting
  college only ever comes from the session (TENANT-001).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CAMPUS = "/api/v1/campus"
ROSTER_HEADER = "roll_number,full_name,department_code,program,admission_year,email"


class Kind(StrEnum):
    OBJECT = "object"
    LIST = "list"
    CREATE = "create"


@dataclass(frozen=True)
class IsolationCase:
    kind: Kind
    # Given the world (tests/integration/campus_world.World), the concrete path and JSON body.
    request: Callable[[Any], tuple[str, dict[str, Any] | None]]


def _static(
    path: str, body: dict[str, Any] | None = None
) -> Callable[[Any], tuple[str, dict[str, Any] | None]]:
    return lambda world: (path, body)


CASES: dict[tuple[str, str], IsolationCase] = {
    # departments
    ("GET", f"{CAMPUS}/departments"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/departments?include_archived=true")
    ),
    ("POST", f"{CAMPUS}/departments"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/departments",
            {"code": "X1", "name": "X", "college_id": str(w.river.id)},
        ),
    ),
    ("GET", f"{CAMPUS}/departments/{{department_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/departments/{w.river.departments['CSE'].id}", None)
    ),
    ("PATCH", f"{CAMPUS}/departments/{{department_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/departments/{w.river.departments['CSE'].id}", {"name": "Hacked"}),
    ),
    # roster
    ("GET", f"{CAMPUS}/roster"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/roster?query=R-001")),
    ("POST", f"{CAMPUS}/roster/import"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/roster/import",
            {
                "csv": ROSTER_HEADER + "\nX,X,CSE,B,2025,",
                "college_id": str(w.river.id),
            },
        ),
    ),
    # invites
    ("GET", f"{CAMPUS}/invites"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/invites")),
    ("POST", f"{CAMPUS}/invites"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/invites",
            {"email": "x@riverside.example", "kind": "STAFF", "college_id": str(w.river.id)},
        ),
    ),
    # members and grants
    ("GET", f"{CAMPUS}/members"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/members?query=River")
    ),
    ("PATCH", f"{CAMPUS}/members/{{membership_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_student'].id}",
            {"status": "ENDED", "reason": "x"},
        ),
    ),
    ("POST", f"{CAMPUS}/members/{{membership_id}}/grants"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_admin'].id}/grants",
            {"role": "ISSUE_COORDINATOR"},
        ),
    ),
    ("DELETE", f"{CAMPUS}/members/{{membership_id}}/grants/{{grant_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_admin'].id}/grants/{w.river_admin_grant.id}",
            None,
        ),
    ),
    # membership requests (approval queue)
    ("GET", f"{CAMPUS}/membership-requests"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/membership-requests")
    ),
    ("POST", f"{CAMPUS}/membership-requests/{{request_id}}/approve"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/membership-requests/{w.river_request.id}/approve", None),
    ),
    ("POST", f"{CAMPUS}/membership-requests/{{request_id}}/reject"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/membership-requests/{w.river_request.id}/reject", {"reason": "x"}),
    ),
    # audit
    ("GET", f"{CAMPUS}/audit-log"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/audit-log")),
}
