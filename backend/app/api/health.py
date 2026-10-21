"""Operational endpoints (architecture.md §16). `/readyz` is added with the database in Step 2."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/healthz")
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")
