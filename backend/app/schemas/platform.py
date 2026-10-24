"""Platform-admin request/response models (architecture.md §11.1 Platform). Unknown fields are
rejected; responses expose college metadata and counts only (ADMIN-008)."""

import re
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any, Literal, Self
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic_core import PydanticCustomError

from app.models import AuditLog, College, Invite
from app.models.user import User
from app.schemas.auth import Email
from app.schemas.campus import MembershipOut

_SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$")
_DOMAIN = re.compile(r"^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$")


@lru_cache
def _timezones() -> frozenset[str]:
    # IANA "Area/Location" names plus UTC; leaves out aliases like "localtime" or "EST5EDT".
    return frozenset(z for z in available_timezones() if "/" in z or z == "UTC")


def _name(value: str) -> str:
    value = " ".join(value.split())
    if not 1 <= len(value) <= 120 or not value.isprintable():
        raise PydanticCustomError("invalid_name", "Use 1 to 120 characters.")
    return value


def _slug(value: str) -> str:
    if not _SLUG.match(value):
        raise PydanticCustomError(
            "invalid_slug", "Use 1 to 50 lower-case letters, digits and hyphens (not at the ends)."
        )
    return value


def _timezone(value: str) -> str:
    if value not in _timezones():
        raise PydanticCustomError("invalid_timezone", "Choose a time zone such as Asia/Kolkata.")
    return value


def _domains(values: list[str]) -> list[str]:
    cleaned = sorted({v.strip().lower() for v in values})
    for domain in cleaned:
        if len(domain) > 253 or not _DOMAIN.match(domain):
            raise PydanticCustomError("invalid_domain", "Enter domains like northfield.edu.")
    return cleaned


Name = Annotated[str, AfterValidator(_name)]
Slug = Annotated[str, AfterValidator(_slug)]
Timezone = Annotated[str, AfterValidator(_timezone)]
Domains = Annotated[list[str], Field(max_length=10), AfterValidator(_domains)]
Reason = Annotated[str, Field(min_length=1, max_length=500)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollegeCreate(_Request):
    name: Name
    slug: Slug
    timezone: Timezone
    email_domains: Domains = []
    is_demo: bool = False


class CollegeUpdate(_Request):
    """The slug is permanent (it's in members' sign-up links); everything else can change."""

    name: Name | None = None
    timezone: Timezone | None = None
    email_domains: Domains | None = None
    status: Literal["ACTIVE", "SUSPENDED", "ONBOARDING"] | None = None
    reason: Reason | None = None

    def detail_changes(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.model_dump(include={"name", "timezone", "email_domains"}).items()
            if v is not None
        }


class AdminInviteCreate(_Request):
    email: Email
    kind: Literal["FACULTY", "STAFF"]
    reason: Reason | None = None


class SuspendRequest(_Request):
    reason: Reason


class UnsuspendRequest(_Request):
    reason: Reason | None = None


class InviteAcceptRequest(_Request):
    token: Annotated[str, Field(min_length=1, max_length=200)]


class PlatformCollegeOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    status: str
    email_domains: list[str]
    is_demo: bool
    created_at: datetime
    active_member_count: int

    @classmethod
    def build(cls, college: College, active_member_count: int) -> Self:
        return cls(
            id=college.id,
            name=college.name,
            slug=college.slug,
            timezone=college.timezone,
            status=college.status,
            email_domains=list(college.email_domains),
            is_demo=college.is_demo,
            created_at=college.created_at,
            active_member_count=active_member_count,
        )


class AdminInviteOut(BaseModel):
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


class PlatformCollegeDetail(PlatformCollegeOut):
    admin_invites: list[AdminInviteOut]


class CollegePage(BaseModel):
    items: list[PlatformCollegeOut]
    next_cursor: str | None


class PlatformUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    status: str
    platform_role: str | None

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            platform_role=user.platform_role,
        )


class UserLookup(BaseModel):
    items: list[PlatformUserOut]


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    college_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AuditLog) -> Self:
        return cls(
            id=entry.id,
            action=entry.action,
            actor_user_id=entry.actor_user_id,
            college_id=entry.college_id,
            target_type=entry.target_type,
            target_id=entry.target_id,
            reason=entry.reason,
            metadata=entry.data,
            created_at=entry.created_at,
        )


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None


class InviteAcceptResponse(BaseModel):
    membership: MembershipOut
