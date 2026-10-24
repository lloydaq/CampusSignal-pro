"""Platform administration routes (architecture.md §11.1 Platform). Platform admins only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import AppSettings, Db, MailerDep, Now, PlatformAdmin, no_store
from app.core.mailer import send_email
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.models import MembershipKind
from app.schemas.auth import Email
from app.schemas.platform import (
    AdminInviteCreate,
    AdminInviteOut,
    AuditEntryOut,
    AuditPage,
    CollegeCreate,
    CollegePage,
    CollegeUpdate,
    PlatformCollegeDetail,
    PlatformCollegeOut,
    PlatformUserOut,
    SuspendRequest,
    UnsuspendRequest,
    UserLookup,
)
from app.services import platform as platform_service

router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(no_store)])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]


@router.get("/colleges")
def list_colleges(
    _: PlatformAdmin, db: Db, cursor: CursorParam = None, limit: Limit = DEFAULT_LIMIT
) -> CollegePage:
    items, next_cursor = platform_service.list_colleges(db, decode_cursor(cursor), limit)
    return CollegePage(
        items=[PlatformCollegeOut.build(s.college, s.active_member_count) for s in items],
        next_cursor=next_cursor,
    )


@router.post("/colleges", status_code=201)
def create_college(
    body: CollegeCreate, admin: PlatformAdmin, db: Db, now: Now
) -> PlatformCollegeOut:
    college = platform_service.create_college(
        db,
        actor=admin,
        name=body.name,
        slug=body.slug,
        timezone=body.timezone,
        email_domains=body.email_domains,
        is_demo=body.is_demo,
        now=now,
    )
    return PlatformCollegeOut.build(college, 0)


def _detail(db: Db, college_id: uuid.UUID, now: Now) -> PlatformCollegeDetail:
    summary = platform_service.get_college(db, college_id)
    invites = [
        AdminInviteOut.build(i, platform_service.invite_state(i, now))
        for i in platform_service.admin_invites(db, college_id)
    ]
    base = PlatformCollegeOut.build(summary.college, summary.active_member_count)
    return PlatformCollegeDetail(**base.model_dump(), admin_invites=invites)


@router.get("/colleges/{college_id}")
def get_college(college_id: uuid.UUID, _: PlatformAdmin, db: Db, now: Now) -> PlatformCollegeDetail:
    return _detail(db, college_id, now)


@router.patch("/colleges/{college_id}")
def update_college(
    college_id: uuid.UUID, body: CollegeUpdate, admin: PlatformAdmin, db: Db, now: Now
) -> PlatformCollegeDetail:
    platform_service.update_college(
        db,
        actor=admin,
        college_id=college_id,
        changes=body.detail_changes(),
        status=body.status,
        reason=body.reason,
        now=now,
    )
    return _detail(db, college_id, now)


@router.post("/colleges/{college_id}/admin-invites", status_code=201)
def invite_college_admin(
    college_id: uuid.UUID,
    body: AdminInviteCreate,
    admin: PlatformAdmin,
    background: BackgroundTasks,
    db: Db,
    settings: AppSettings,
    mailer: MailerDep,
    now: Now,
) -> AdminInviteOut:
    invite, emails = platform_service.invite_college_admin(
        db,
        settings,
        actor=admin,
        college_id=college_id,
        email=body.email,
        kind=MembershipKind(body.kind),
        reason=body.reason,
        now=now,
    )
    for email in emails:
        background.add_task(send_email, mailer, email)
    return AdminInviteOut.build(invite, "PENDING")


@router.get("/users")
def find_user(email: Annotated[Email, Query()], _: PlatformAdmin, db: Db) -> UserLookup:
    """Exact email lookup only: there is no browsing or partial search of accounts."""
    user = platform_service.find_user(db, email)
    return UserLookup(items=[PlatformUserOut.from_user(user)] if user else [])


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: uuid.UUID, body: SuspendRequest, admin: PlatformAdmin, db: Db
) -> PlatformUserOut:
    user = platform_service.suspend_user(db, actor=admin, user_id=user_id, reason=body.reason)
    return PlatformUserOut.from_user(user)


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(
    user_id: uuid.UUID, body: UnsuspendRequest, admin: PlatformAdmin, db: Db
) -> PlatformUserOut:
    user = platform_service.unsuspend_user(db, actor=admin, user_id=user_id, reason=body.reason)
    return PlatformUserOut.from_user(user)


@router.get("/audit-log")
def audit_log(
    _: PlatformAdmin, db: Db, cursor: CursorParam = None, limit: Limit = DEFAULT_LIMIT
) -> AuditPage:
    entries, next_cursor = platform_service.platform_audit(db, decode_cursor(cursor), limit)
    return AuditPage(items=[AuditEntryOut.from_entry(e) for e in entries], next_cursor=next_cursor)
