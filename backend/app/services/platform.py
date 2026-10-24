"""Platform administration (ADMIN-001…004, ADMIN-007 platform side; architecture.md §9).

Platform admins manage colleges as tenants and user accounts as identities. They see college
metadata and counts, never college content, members' names or academic data (ADMIN-008):
this module only reads `colleges`, `invites` it issued, `users` by exact email, and
platform-level audit entries.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.mailer import OutgoingEmail
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    AuditLog,
    College,
    CollegeMembership,
    Invite,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)
from app.models.user import User, UserStatus
from app.policies.platform import (
    can_change_college_status,
    can_suspend_user,
    can_unsuspend_user,
    college_status_change_needs_reason,
    is_platform_admin,
)
from app.services import sessions
from app.services.audit import record_audit
from app.services.invites import create_invite, invite_email

ACTION_COLLEGE_CREATED = "platform.college_created"
ACTION_COLLEGE_UPDATED = "platform.college_updated"
ACTION_COLLEGE_STATUS_CHANGED = "platform.college_status_changed"
ACTION_ADMIN_INVITED = "platform.admin_invited"
ACTION_USER_SUSPENDED = "platform.user_suspended"
ACTION_USER_UNSUSPENDED = "platform.user_unsuspended"
PLATFORM_ACTION_PREFIX = "platform."


@dataclass(frozen=True)
class CollegeSummary:
    college: College
    active_member_count: int


# --- colleges ------------------------------------------------------------------------------


def _member_counts(db: Session, college_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not college_ids:
        return {}
    rows = db.execute(
        select(CollegeMembership.college_id, func.count())
        .where(
            CollegeMembership.college_id.in_(college_ids),
            CollegeMembership.status == MembershipStatus.ACTIVE,
        )
        .group_by(CollegeMembership.college_id)
    ).all()
    return {college_id: count for college_id, count in rows}


def list_colleges(
    db: Session, cursor: Cursor | None, limit: int
) -> tuple[list[CollegeSummary], str | None]:
    rows = list(
        db.execute(newest_first(select(College), College.created_at, College.id, cursor, limit))
        .scalars()
        .all()
    )
    items, next_cursor = split_page(rows, limit, lambda c: (c.created_at, c.id))
    counts = _member_counts(db, [c.id for c in items])
    return [CollegeSummary(c, counts.get(c.id, 0)) for c in items], next_cursor


def get_college(db: Session, college_id: uuid.UUID) -> CollegeSummary:
    college = db.execute(select(College).where(College.id == college_id)).scalar_one_or_none()
    if college is None:
        raise NotFound()
    return CollegeSummary(college, _member_counts(db, [college.id]).get(college.id, 0))


def create_college(
    db: Session,
    *,
    actor: User,
    name: str,
    slug: str,
    timezone: str,
    email_domains: list[str],
    is_demo: bool,
    now: datetime,
) -> College:
    college = College(
        name=name,
        slug=slug,
        timezone=timezone,
        email_domains=email_domains,
        is_demo=is_demo,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(college)
            db.flush()
    except IntegrityError:
        raise Conflict("A college with this slug already exists.", code="slug_taken") from None
    record_audit(
        db,
        action=ACTION_COLLEGE_CREATED,
        actor_user_id=actor.id,
        college_id=college.id,
        target_type="college",
        target_id=str(college.id),
        metadata={"slug": slug, "is_demo": is_demo},
    )
    db.commit()
    return college


def update_college(
    db: Session,
    *,
    actor: User,
    college_id: uuid.UUID,
    changes: dict[str, Any],
    status: str | None,
    reason: str | None,
    now: datetime,
) -> College:
    college = db.execute(
        select(College).where(College.id == college_id).with_for_update()
    ).scalar_one_or_none()
    if college is None:
        raise NotFound()
    if status is not None and status != college.status:
        if not can_change_college_status(college.status, status):
            raise Conflict(
                f"A college can't go from {college.status} to {status}.",
                code="invalid_transition",
            )
        if college_status_change_needs_reason(status) and not reason:
            raise ValidationFailed.field("reason", "Give a reason for suspending the college.")
        record_audit(
            db,
            action=ACTION_COLLEGE_STATUS_CHANGED,
            actor_user_id=actor.id,
            college_id=college.id,
            target_type="college",
            target_id=str(college.id),
            reason=reason,
            metadata={"from": college.status, "to": status},
        )
        college.status = status
    changed = {k: v for k, v in changes.items() if getattr(college, k) != v}
    if changed:
        for key, value in changed.items():
            setattr(college, key, value)
        record_audit(
            db,
            action=ACTION_COLLEGE_UPDATED,
            actor_user_id=actor.id,
            college_id=college.id,
            target_type="college",
            target_id=str(college.id),
            metadata={"fields": sorted(changed)},
        )
    college.updated_at = now
    db.commit()
    return college


# --- first college admin invites (ADMIN-002) ------------------------------------------------


def _active_college_admin_emails(db: Session, college_id: uuid.UUID) -> list[str]:
    rows = db.execute(
        select(User.email)
        .join(CollegeMembership, CollegeMembership.user_id == User.id)
        .join(
            RoleGrant,
            (RoleGrant.college_id == CollegeMembership.college_id)
            & (RoleGrant.membership_id == CollegeMembership.id),
        )
        .where(
            CollegeMembership.college_id == college_id,
            CollegeMembership.status == MembershipStatus.ACTIVE,
            RoleGrant.role == Role.COLLEGE_ADMIN,
        )
        .distinct()
    ).scalars()
    return sorted(rows)


def invite_college_admin(
    db: Session,
    settings: Settings,
    *,
    actor: User,
    college_id: uuid.UUID,
    email: str,
    kind: MembershipKind,
    reason: str | None,
    now: datetime,
) -> tuple[Invite, list[OutgoingEmail]]:
    college = db.execute(select(College).where(College.id == college_id)).scalar_one_or_none()
    if college is None:
        raise NotFound()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None and is_platform_admin(existing):
        # P-7: it could never be accepted; say so now rather than at acceptance.
        raise ValidationFailed.field("email", "Platform admin accounts can't join a college.")
    current_admins = _active_college_admin_emails(db, college.id)
    if current_admins and not reason:
        raise ValidationFailed.field(
            "reason",
            "This college already has a college admin. Give a reason for inviting another.",
        )
    invite, token = create_invite(
        db,
        college=college,
        email=email,
        kind=kind,
        grants=[{"role": Role.COLLEGE_ADMIN}],
        invited_by=actor,
        now=now,
    )
    record_audit(
        db,
        action=ACTION_ADMIN_INVITED,
        actor_user_id=actor.id,
        college_id=college.id,
        target_type="invite",
        target_id=str(invite.id),
        reason=reason,
        metadata={"kind": kind, "existing_admins_notified": len(current_admins)},
    )
    db.commit()
    emails = [invite_email(settings, college, email, token, admin=True)]
    emails += [
        OutgoingEmail(
            to=admin_email,
            subject=f"Another college admin was invited to {college.name}",
            text=(
                "A CampusSignal platform admin invited another college admin to "
                f"{college.name}.\n\n"
                f"Reason given: {reason}\n\n"
                "If you didn't expect this, contact CampusSignal support.\n"
            ),
        )
        for admin_email in current_admins
    ]
    return invite, emails


def admin_invites(db: Session, college_id: uuid.UUID) -> list[Invite]:
    """Invites carrying a COLLEGE_ADMIN grant, newest first (what the platform issued)."""
    rows = db.execute(
        select(Invite)
        .where(
            Invite.college_id == college_id,
            Invite.grants.contains([{"role": Role.COLLEGE_ADMIN}]),
        )
        .order_by(Invite.created_at.desc(), Invite.id.desc())
        .limit(50)
    ).scalars()
    return list(rows)


def invite_state(invite: Invite, now: datetime) -> str:
    if invite.accepted_at is not None:
        return "ACCEPTED"
    if invite.revoked_at is not None:
        return "REVOKED"
    if invite.expires_at <= now:
        return "EXPIRED"
    return "PENDING"


# --- users (ADMIN-004) ---------------------------------------------------------------------


def find_user(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFound()
    return user


def suspend_user(db: Session, *, actor: User, user_id: uuid.UUID, reason: str) -> User:
    user = _user(db, user_id)
    if user.id == actor.id:
        raise Conflict("You can't suspend your own account.", code="cannot_suspend_self")
    if not can_suspend_user(actor, user):
        raise Conflict("Only active accounts can be suspended.", code="invalid_transition")
    user.status = UserStatus.SUSPENDED
    sessions.revoke_all_sessions(db, user.id)  # AUTH-009: immediately
    record_audit(
        db,
        action=ACTION_USER_SUSPENDED,
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user.id),
        reason=reason,
    )
    db.commit()
    return user


def unsuspend_user(db: Session, *, actor: User, user_id: uuid.UUID, reason: str | None) -> User:
    user = _user(db, user_id)
    if not can_unsuspend_user(user):
        raise Conflict("Only suspended accounts can be reinstated.", code="invalid_transition")
    user.status = UserStatus.ACTIVE
    record_audit(
        db,
        action=ACTION_USER_UNSUSPENDED,
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user.id),
        reason=reason,
    )
    db.commit()
    return user


# --- platform audit log (ADMIN-007) --------------------------------------------------------


def platform_audit(
    db: Session, cursor: Cursor | None, limit: int
) -> tuple[list[AuditLog], str | None]:
    query = select(AuditLog).where(
        AuditLog.action.startswith(PLATFORM_ACTION_PREFIX, autoescape=True)
    )
    rows = list(
        db.execute(newest_first(query, AuditLog.created_at, AuditLog.id, cursor, limit)).scalars()
    )
    return split_page(rows, limit, lambda e: (e.created_at, e.id))
