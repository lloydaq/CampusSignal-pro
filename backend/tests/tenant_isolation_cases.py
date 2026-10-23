"""Registry for the tenant-isolation suite (TENANT-005, PRD §17).

Every /api/v1/campus operation must be listed here with a cross-college probe: the suite
seeds Northfield Institute and Riverside College, signs in as a Northfield member, and calls
the operation on Riverside's object, expecting the same 404 as for an object that doesn't
exist (TENANT-002) and no Riverside data in the body. `test_route_inventory` fails when a
campus route is missing from this registry, so a new route can't skip the suite.

Phase 3a has no campus routes yet; 3b onwards add entries as they add routes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IsolationCase:
    # Builds the request for a Riverside object: (path with ids filled in, JSON body or None).
    request: Callable[[Any], tuple[str, dict[str, Any] | None]]
    # Operations without an object id (lists, creates) state what proves isolation instead.
    note: str = ""


CASES: dict[tuple[str, str], IsolationCase] = {}
