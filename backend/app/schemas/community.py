"""Community shapes (COMMUNITY-001…005; architecture.md §11.1). Requests reject unknown fields,
so a body that names a college, an author, a department or a status is a 422: the college
comes from the session, a department post goes to the poster's own department, and status is
for moderators. Posts are plain text; the page turns URLs into links (COMMUNITY-001).
"""

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models import PostVisibility, ReportReason
from app.schemas.campus import DepartmentRef

POST_MAX = 5000
COMMENT_MAX = 2000

# Control characters other than tab and newline.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _text(limit: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not 1 <= len(value) <= limit or _CONTROL.search(value):
            raise PydanticCustomError("invalid_text", f"Use 1 to {limit:,} characters.")
        return value

    return check


PostBody = Annotated[str, AfterValidator(_text(POST_MAX))]
CommentBody = Annotated[str, AfterValidator(_text(COMMENT_MAX))]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostCreate(_Request):
    body: PostBody
    visibility: PostVisibility


class PostEdit(_Request):
    body: PostBody


class CommentCreate(_Request):
    body: CommentBody


class CommentEdit(_Request):
    body: CommentBody


class Author(BaseModel):
    """Name and kind: faculty and staff get a role badge (COMMUNITY-009). Never contacts."""

    name: str
    kind: str


class PostOut(BaseModel):
    id: uuid.UUID
    body: str
    visibility: str
    department: DepartmentRef | None
    author: Author
    status: str
    hidden_reason: str | None  # only its author and moderators ever see a hidden post
    edited_at: datetime | None
    created_at: datetime
    reaction_count: int
    comment_count: int
    reacted: bool
    can_edit: bool
    can_delete: bool
    can_engage: bool  # comment and react


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None


class CommentOut(BaseModel):
    id: uuid.UUID
    body: str
    author: Author
    status: str
    hidden_reason: str | None
    edited_at: datetime | None
    created_at: datetime
    can_edit: bool
    can_delete: bool


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: str | None


class ReactionOut(BaseModel):
    reacted: bool
    reaction_count: int


Reason = Annotated[str, Field(min_length=1, max_length=500)]


class ReportCreate(_Request):
    """A report names exactly one target: a post or a comment (COMMUNITY-006)."""

    post_id: uuid.UUID | None = None
    comment_id: uuid.UUID | None = None
    reason: ReportReason
    note: Reason | None = None

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if (self.post_id is None) == (self.comment_id is None):
            raise PydanticCustomError("one_target", "Report either a post or a comment.")
        return self


class ReportOut(BaseModel):
    id: uuid.UUID
    status: str


class ReportedContent(BaseModel):
    """What a moderator needs to decide; who reported it stays private."""

    type: str  # post | comment
    post_id: uuid.UUID
    comment_id: uuid.UUID | None
    body: str
    author: Author
    visibility: str
    department: DepartmentRef | None
    status: str
    hidden_reason: str | None  # what its author was told, once hidden


class QueueItemOut(BaseModel):
    id: uuid.UUID
    reason: str
    note: str | None
    status: str
    created_at: datetime
    handled_at: datetime | None  # set once hidden or dismissed
    open_reports: int  # on the same content, this one included
    content: ReportedContent


class QueuePage(BaseModel):
    items: list[QueueItemOut]
    next_cursor: str | None


class Resolve(_Request):
    """HIDE needs the reason its author will read; DISMISS may say why (audit log only)."""

    action: Annotated[str, Field(pattern="^(HIDE|DISMISS)$")]
    reason: Reason | None = None

    @model_validator(mode="after")
    def _hiding_needs_a_reason(self) -> Self:
        if self.action == "HIDE" and not (self.reason and self.reason.strip()):
            raise PydanticCustomError(
                "reason_required", "Say why it's hidden; its author sees this."
            )
        return self


class ResolveOut(BaseModel):
    action: str
    closed_reports: int
