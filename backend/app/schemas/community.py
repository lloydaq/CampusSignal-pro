"""Community shapes (COMMUNITY-001…005; architecture.md §11.1). Requests reject unknown fields,
so a body that names a college, an author, a department or a status is a 422: the college
comes from the session, a department post goes to the poster's own department, and status is
for moderators. Posts are plain text; the page turns URLs into links (COMMUNITY-001).
"""

import re
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic_core import PydanticCustomError

from app.models import PostVisibility
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
