"""Operational endpoints (architecture.md §16)."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core import db
from app.core.errors import NotReady

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/healthz")
def healthz() -> HealthResponse:
    """Process is up. Does not touch the database."""
    return HealthResponse(status="ok")


@router.get("/readyz")
def readyz(request: Request) -> HealthResponse:
    """Database reachable and migrated to head; otherwise 503 `not_ready`."""
    problem = db.check_readiness(request.app.state.engine, db.expected_migration_heads())
    if problem is db.ReadinessProblem.DATABASE_UNREACHABLE:
        raise NotReady(details={"database": problem.value})
    if problem is db.ReadinessProblem.MIGRATIONS_PENDING:
        raise NotReady(details={"migrations": problem.value})
    return HealthResponse(status="ready")
