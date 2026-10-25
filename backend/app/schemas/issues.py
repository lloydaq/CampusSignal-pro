"""Campus issue shapes (ISSUE-001, 005, 006; architecture.md §11.1). Requests reject unknown
fields, so a body that names a college, a reporter or a status is a 422: the college comes from
the session and an issue always starts SUBMITTED. Responses whitelist fields; a duplicate's
original is reduced to its status and resolution time unless the viewer may read it (ISSUE-006).
"""

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic_core import PydanticCustomError

from app.models import IssueCategory

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _line(limit: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        value = " ".join(value.split())
        if not 1 <= len(value) <= limit or _CONTROL.search(value):
            raise PydanticCustomError("invalid_text", f"Use 1 to {limit:,} characters.")
        return value

    return check


def _text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 1 <= len(value) <= 3000 or _CONTROL.search(value):
        raise PydanticCustomError("invalid_text", "Use 1 to 3,000 characters.")
    return value


Title = Annotated[str, AfterValidator(_line(120))]
Location = Annotated[str, AfterValidator(_line(200))]
Room = Annotated[str, AfterValidator(_line(100))]
Description = Annotated[str, AfterValidator(_text)]


class IssueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: IssueCategory
    title: Title
    description: Description
    location: Location
    room: Room | None = None


class IssueSummary(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    location: str
    room: str | None
    status: str
    reporter_name: str
    assignee_name: str | None
    created_at: datetime
    updated_at: datetime


class IssueUpdateOut(BaseModel):
    id: uuid.UUID
    kind: str
    from_status: str | None
    to_status: str | None
    body: str | None
    is_internal: bool
    actor_name: str | None  # None: a change the system made
    created_at: datetime


class DuplicateOf(BaseModel):
    """The issue this one duplicates. Its reporter sees only `status` and `resolved_at`;
    `id` is filled in only for someone who may read the original (ISSUE-006)."""

    id: uuid.UUID | None
    status: str
    resolved_at: datetime | None


class IssueDetail(IssueSummary):
    description: str
    resolved_at: datetime | None
    version: int
    duplicate_of: DuplicateOf | None
    updates: list[IssueUpdateOut]


class IssuePage(BaseModel):
    items: list[IssueSummary]
    next_cursor: str | None
