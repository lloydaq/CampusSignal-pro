"""The college directory used when joining (architecture.md §9: the only cross-college data in
the MVP)."""

from fastapi import APIRouter

from app.api.deps import Auth, Db
from app.schemas.membership import CollegeDirectory, CollegeListing
from app.services.membership_requests import active_colleges

router = APIRouter(prefix="/colleges", tags=["colleges"])


@router.get("")
def list_colleges(_: Auth, db: Db) -> CollegeDirectory:
    return CollegeDirectory(
        items=[CollegeListing(name=c.name, slug=c.slug) for c in active_colleges(db)]
    )
