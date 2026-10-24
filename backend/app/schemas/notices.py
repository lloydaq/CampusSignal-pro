"""Notice shapes (architecture.md §11.1). Requests reject unknown fields, so a body that tries
to name a college, an author, a status or a schedule (`publish_at`, `audience`: P1, deferred by
P-9) is a 422. Responses whitelist: the author's name goes only to people who can manage the
notice."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models import Department, Notice, NoticeCategory, NoticePriority, NoticeScope
from app.schemas.campus import DepartmentRef

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EXCERPT_MARKUP = re.compile(r"\[([^\]]*)\]\([^)]*\)|[*_`#>]|^\s*[-+]\s+", re.MULTILINE)
EXCERPT_LENGTH = 160


def _title(value: str) -> str:
    value = " ".join(value.split())
    if not 1 <= len(value) <= 150 or _CONTROL.search(value):
        raise PydanticCustomError("invalid_title", "Use 1 to 150 characters.")
    return value


def _body(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 1 <= len(value) <= 10_000 or _CONTROL.search(value):
        raise PydanticCustomError("invalid_body", "Use 1 to 10,000 characters.")
    return value


Title = Annotated[str, AfterValidator(_title)]
Body = Annotated[str, AfterValidator(_body)]
Reason = Annotated[str, Field(min_length=1, max_length=500)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoticeCreate(_Request):
    title: Title
    body: Body
    category: NoticeCategory
    priority: NoticePriority = NoticePriority.NORMAL
    scope: NoticeScope
    department_id: uuid.UUID | None = None
    expires_at: AwareDatetime | None = None
    publish: bool = False

    @model_validator(mode="after")
    def _department_matches_scope(self) -> Self:
        if (self.scope == NoticeScope.DEPARTMENT) != (self.department_id is not None):
            raise PydanticCustomError(
                "department_required",
                "A department notice needs a department; a college notice takes none.",
            )
        return self


class NoticeUpdate(_Request):
    """Only what was sent changes. The scope and department are fixed once a notice exists:
    moving a notice between audiences would show it to people it wasn't written for."""

    version: Annotated[int, Field(ge=1)]
    title: Title | None = None
    body: Body | None = None
    category: NoticeCategory | None = None
    priority: NoticePriority | None = None
    expires_at: AwareDatetime | None = None  # send null to clear it

    @model_validator(mode="after")
    def _something_changes(self) -> Self:
        if not (self.model_fields_set - {"version"}):
            raise PydanticCustomError("nothing_to_change", "Send at least one field to change.")
        for required in ("title", "body", "category", "priority"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise PydanticCustomError("required", f"{required} can't be empty.")
        return self


class NoticePublish(_Request):
    version: Annotated[int, Field(ge=1)]


class NoticeWithdraw(_Request):
    reason: Reason


def excerpt(body: str) -> str:
    text = " ".join(_EXCERPT_MARKUP.sub(lambda m: m.group(1) or "", body).split())
    return text if len(text) <= EXCERPT_LENGTH else text[: EXCERPT_LENGTH - 1].rstrip() + "…"


class NoticeSummary(BaseModel):
    id: uuid.UUID
    title: str
    excerpt: str
    category: str
    priority: str
    scope: str
    department: DepartmentRef | None
    status: str
    pinned: bool
    expired: bool
    published_at: datetime | None
    expires_at: datetime | None
    edited_at: datetime | None
    created_at: datetime
    can_manage: bool


class NoticeDetail(NoticeSummary):
    body: str
    version: int
    author_name: str | None  # only for people who can manage the notice


class NoticePage(BaseModel):
    items: list[NoticeSummary]
    next_cursor: str | None


def _common(
    notice: Notice, department: Department | None, *, pinned: bool, expired: bool, can_manage: bool
) -> dict[str, Any]:
    return {
        "id": notice.id,
        "title": notice.title,
        "category": notice.category,
        "priority": notice.priority,
        "scope": notice.scope,
        "department": DepartmentRef.from_department(department) if department else None,
        "status": notice.status,
        "pinned": pinned,
        "expired": expired,
        "published_at": notice.published_at,
        "expires_at": notice.expires_at,
        "edited_at": notice.edited_at,
        "created_at": notice.created_at,
        "can_manage": can_manage,
    }


def summary(
    notice: Notice, department: Department | None, *, pinned: bool, expired: bool, can_manage: bool
) -> NoticeSummary:
    return NoticeSummary(
        **_common(notice, department, pinned=pinned, expired=expired, can_manage=can_manage),
        excerpt=excerpt(notice.body),
    )


def detail(
    notice: Notice,
    department: Department | None,
    author_name: str | None,
    *,
    pinned: bool,
    expired: bool,
    can_manage: bool,
) -> NoticeDetail:
    return NoticeDetail(
        **_common(notice, department, pinned=pinned, expired=expired, can_manage=can_manage),
        excerpt=excerpt(notice.body),
        body=notice.body,
        version=notice.version,
        author_name=author_name if can_manage else None,
    )
