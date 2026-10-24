"""College administration shapes (architecture.md §11.1). Requests never carry `college_id`,
roles of the caller or statuses beyond what each route changes (PRD §17.4: unknown fields are
422). Responses follow PRD §17.6: contact details only where the caller may see them."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models import AuditLog, Department, Invite
from app.schemas.auth import Email
from app.schemas.campus import DepartmentRef

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,15}$")


def _code(value: str) -> str:
    value = value.strip().upper()
    if not _CODE.match(value):
        raise PydanticCustomError(
            "invalid_code",
            "Use 1 to 16 letters, digits or hyphens, starting with a letter or digit.",
        )
    return value


def _name(value: str) -> str:
    value = " ".join(value.split())
    if not 1 <= len(value) <= 120 or not value.isprintable():
        raise PydanticCustomError("invalid_name", "Use 1 to 120 characters.")
    return value


Code = Annotated[str, AfterValidator(_code)]
Name = Annotated[str, AfterValidator(_name)]
Description = Annotated[str, Field(max_length=2000)]
Reason = Annotated[str, Field(min_length=1, max_length=500)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- departments ---------------------------------------------------------------------------


class DepartmentCreate(_Request):
    code: Code
    name: Name
    description: Description = ""


class DepartmentUpdate(_Request):
    """The code is permanent (roster files refer to it)."""

    name: Name | None = None
    description: Description | None = None
    archived: bool | None = None


class DepartmentOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    archived: bool

    @classmethod
    def from_department(cls, department: Department) -> Self:
        return cls(
            id=department.id,
            code=department.code,
            name=department.name,
            description=department.description,
            archived=department.archived_at is not None,
        )


class DepartmentPage(DepartmentOut):
    """DEPT-003: the department's page data. Admins are names only."""

    admins: list[str]


class DepartmentList(BaseModel):
    items: list[DepartmentOut]


# --- roster --------------------------------------------------------------------------------


class RosterImport(_Request):
    # The body limit (1 MiB) bounds this; the service also caps the row count.
    csv: Annotated[str, Field(max_length=1_000_000)]


class RosterImported(BaseModel):
    imported: int


class RosterEntryOut(BaseModel):
    id: uuid.UUID
    roll_number: str
    full_name: str
    email: str | None
    program: str
    admission_year: int
    department: DepartmentRef
    claimed: bool


class RosterPage(BaseModel):
    items: list[RosterEntryOut]
    next_cursor: str | None


# --- invites -------------------------------------------------------------------------------


class InviteCreate(_Request):
    email: Email
    kind: Literal["FACULTY", "STAFF"]  # students join through the roster (MEMBER-002)


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    kind: str
    state: Literal["PENDING", "ACCEPTED", "EXPIRED", "REVOKED"]
    created_at: datetime
    expires_at: datetime

    @classmethod
    def build(cls, invite: Invite, state: str) -> Self:
        return cls.model_validate(
            {
                "id": invite.id,
                "email": invite.email,
                "kind": invite.kind,
                "state": state,
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
            }
        )


class InviteList(BaseModel):
    items: list[InviteOut]


# --- members and roles ---------------------------------------------------------------------


class GrantOut(BaseModel):
    id: uuid.UUID
    role: str
    department: DepartmentRef | None


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    kind: str
    status: str
    department: DepartmentRef | None
    email: str | None  # None when the caller may not see it (PRD §17.6)
    roll_number: str | None
    roles: list[GrantOut]
    joined_at: datetime


class MemberPage(BaseModel):
    items: list[MemberOut]
    next_cursor: str | None


class MemberUpdate(_Request):
    department_id: uuid.UUID | None = None
    status: Literal["ACTIVE", "SUSPENDED", "ENDED"] | None = None
    reason: Reason | None = None


class GrantCreate(_Request):
    role: Literal["COLLEGE_ADMIN", "DEPARTMENT_ADMIN", "ISSUE_COORDINATOR"]
    department_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _department_only_for_department_admin(self) -> Self:
        if (self.role == "DEPARTMENT_ADMIN") != (self.department_id is not None):
            raise PydanticCustomError(
                "department_required",
                "DEPARTMENT_ADMIN needs a department_id; other roles take none.",
            )
        return self


# --- audit ---------------------------------------------------------------------------------


class ActorRef(BaseModel):
    id: uuid.UUID
    display_name: str


class CollegeAuditEntry(BaseModel):
    id: uuid.UUID
    action: str
    actor: ActorRef | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def build(cls, entry: AuditLog, actor: ActorRef | None) -> Self:
        return cls(
            id=entry.id,
            action=entry.action,
            actor=actor,
            target_type=entry.target_type,
            target_id=entry.target_id,
            reason=entry.reason,
            metadata=entry.data,
            created_at=entry.created_at,
        )


class CollegeAuditPage(BaseModel):
    items: list[CollegeAuditEntry]
    next_cursor: str | None
