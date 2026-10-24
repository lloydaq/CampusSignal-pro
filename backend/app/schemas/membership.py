"""Joining a college and the approval queue (architecture.md §11.1). The requester's shapes
never carry verification flags or roster details (MEMBER-004)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.campus import DepartmentRef, MembershipOut


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollegeListing(BaseModel):
    name: str
    slug: str


class CollegeDirectory(BaseModel):
    items: list[CollegeListing]


class MembershipRequestCreate(_Request):
    college_slug: Annotated[str, Field(min_length=1, max_length=50)]
    # Format is checked by the service after the rate limit counts the attempt (MEMBER-010).
    roll_number: Annotated[str, Field(min_length=1, max_length=100)]


class JoinResult(BaseModel):
    status: Literal["ACTIVE", "PENDING"]
    message: str
    membership: MembershipOut | None = None  # only when joined (PENDING answers are uniform)


class MyRequestOut(BaseModel):
    id: uuid.UUID
    college: CollegeListing
    status: Literal["PENDING", "REJECTED"]
    decision_reason: str | None
    created_at: datetime


class MyRequests(BaseModel):
    items: list[MyRequestOut]


class Requester(BaseModel):
    display_name: str
    email: str  # verified (MEMBER-006 shows it next to the roster's details)


class RosterEvidence(BaseModel):
    full_name: str
    program: str
    admission_year: int
    department: DepartmentRef | None


class QueueItem(BaseModel):
    id: uuid.UUID
    requester: Requester
    flag: str | None
    roll_number: str | None
    roster: RosterEvidence | None
    status: str
    decision_reason: str | None
    created_at: datetime


class QueuePage(BaseModel):
    items: list[QueueItem]
    next_cursor: str | None


class RejectRequest(_Request):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class Decision(BaseModel):
    id: uuid.UUID
    status: str
