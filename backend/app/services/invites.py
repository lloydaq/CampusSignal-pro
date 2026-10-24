"""Email invitations to a college (MEMBER-007, ADMIN-002) and their acceptance.

Invites are single-use, bound to one email address, valid for 7 days; only the token's
SHA-256 digest is stored. Issuing a new invite for the same college and address revokes the
older unaccepted ones. College admins' faculty/staff invites (3c) use the same functions.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import Settings
from app.core.errors import BadRequest, Conflict, Forbidden, ValidationFailed
from app.core.mailer import OutgoingEmail
from app.core.ratelimit import Limit
from app.core.security import new_token, token_digest
from app.models import (
    College,
    CollegeMembership,
    Invite,
    MembershipStatus,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext, can_manage_college
from app.policies.platform import invite_acceptance_problem, is_platform_admin
from app.services import sessions
from app.services.audit import record_audit

INVITE_TTL = timedelta(days=7)
INVITE_ATTEMPTS_IP = Limit("invite:ip", 30, timedelta(minutes=15))
ACTION_INVITE_ACCEPTED = "membership.invite_accepted"

_FORBIDDEN_MESSAGES = {
    "platform_admin_cannot_join": (
        "Platform admin accounts can't join a college. Use a separate account."
    ),
    "invite_email_mismatch": (
        "This invitation is for a different email address. Sign in with that address to accept it."
    ),
    "college_inactive": "This college isn't available right now.",
}


def create_invite(
    db: Session,
    *,
    college: College,
    email: str,
    kind: str,
    grants: list[dict[str, Any]],
    invited_by: User,
    now: datetime,
) -> tuple[Invite, str]:
    """Add an invite (the caller commits) and return it with the token for the email."""
    db.execute(
        update(Invite)
        .where(
            Invite.college_id == college.id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token, digest = new_token()
    invite = Invite(
        college_id=college.id,
        email=email,
        kind=kind,
        grants=grants,
        token_hash=digest,
        invited_by_user_id=invited_by.id,
        created_at=now,
        expires_at=now + INVITE_TTL,
    )
    db.add(invite)
    db.flush()
    return invite, token


def invite_email(
    settings: Settings, college: College, email: str, token: str, *, admin: bool
) -> OutgoingEmail:
    origin = str(settings.app_origin).rstrip("/")
    role = "a college admin" if admin else "a member of staff"
    return OutgoingEmail(
        to=email,
        subject=f"You're invited to {college.name} on CampusSignal",
        text=(
            f"You've been invited to join {college.name} on CampusSignal as {role}.\n\n"
            f"Sign in (or create an account) with this email address, then open:\n\n"
            f"{origin}/invites/accept#token={token}\n\n"
            "This link works once and expires in 7 days. "
            "If you weren't expecting it, you can ignore this email.\n"
        ),
    )


def _token_error(invite: Invite | None, now: datetime) -> BadRequest:
    if invite is None or invite.revoked_at is not None:
        return BadRequest("This invitation isn't valid.", code="token_invalid")
    if invite.accepted_at is not None:
        return BadRequest("This invitation was already used.", code="token_used")
    if invite.expires_at <= now:
        return BadRequest("This invitation has expired. Ask for a new one.", code="token_expired")
    return BadRequest("This invitation isn't valid.", code="token_invalid")


def accept_invite(
    db: Session,
    *,
    user: User,
    token: str,
    session_token: str | None,
    ip_key: str,
    now: datetime,
) -> CollegeMembership:
    ratelimit.consume(db, INVITE_ATTEMPTS_IP, ip_key, now)  # commits: failures still count
    # Lock the invite so two concurrent acceptances can't both succeed.
    invite = db.execute(
        select(Invite).where(Invite.token_hash == token_digest(token)).with_for_update()
    ).scalar_one_or_none()
    if invite is None or invite.revoked_at or invite.accepted_at or invite.expires_at <= now:
        raise _token_error(invite, now)
    college = db.execute(select(College).where(College.id == invite.college_id)).scalar_one()
    problem = invite_acceptance_problem(user, invite.email, college)
    if problem is not None:
        raise Forbidden(_FORBIDDEN_MESSAGES[problem], code=problem)

    membership = _membership_for(db, user, college, invite.kind)
    existing = {
        (g.role, g.department_id)
        for g in db.execute(
            select(RoleGrant).where(
                RoleGrant.college_id == college.id, RoleGrant.membership_id == membership.id
            )
        ).scalars()
    }
    for item in invite.grants:
        role, department = item["role"], item.get("department_id")
        department_id = uuid.UUID(department) if department else None
        if (role, department_id) not in existing:
            db.add(
                RoleGrant(
                    college_id=college.id,
                    membership_id=membership.id,
                    role=role,
                    department_id=department_id,
                    granted_by_user_id=invite.invited_by_user_id,
                )
            )
    invite.accepted_at = now
    invite.accepted_by_user_id = user.id
    if user.email_verified_at is None:
        user.email_verified_at = now  # MEMBER-007: the invite proved the address
    sessions.revoke_other_sessions(
        db, user.id, keep=token_digest(session_token) if session_token else None
    )
    record_audit(
        db,
        action=ACTION_INVITE_ACCEPTED,
        actor_user_id=user.id,
        college_id=college.id,
        target_type="membership",
        target_id=str(membership.id),
        metadata={"kind": membership.kind, "roles": [g["role"] for g in invite.grants]},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("You're already a member of a college.", code="already_member") from None
    return membership


def _membership_for(db: Session, user: User, college: College, kind: str) -> CollegeMembership:
    """The ACTIVE membership the invite applies to: the user's existing one in this college,
    or a new one. MEMBER-008: an ACTIVE membership elsewhere blocks acceptance."""
    open_memberships = (
        db.execute(
            select(CollegeMembership).where(
                CollegeMembership.user_id == user.id,
                CollegeMembership.status.in_(
                    (MembershipStatus.ACTIVE, MembershipStatus.PENDING, MembershipStatus.SUSPENDED)
                ),
            )
        )
        .scalars()
        .all()
    )
    for membership in open_memberships:
        if membership.status == MembershipStatus.ACTIVE and membership.college_id == college.id:
            return membership
        if membership.status == MembershipStatus.ACTIVE:
            raise Conflict("You're already a member of another college.", code="already_member")
        if membership.college_id == college.id:
            raise Conflict(
                "You already have a request or suspended membership at this college.",
                code="membership_open",
            )
    membership = CollegeMembership(
        user_id=user.id, college_id=college.id, kind=kind, status=MembershipStatus.ACTIVE
    )
    db.add(membership)
    db.flush()
    return membership


# --- faculty and staff invites from college admins (MEMBER-007) ----------------------------

ACTION_INVITE_SENT = "college.invite_sent"


def invite_member(
    db: Session,
    settings: Settings,
    campus: CampusContext,
    *,
    email: str,
    kind: str,
    now: datetime,
) -> tuple[Invite, OutgoingEmail]:
    if not can_manage_college(campus):
        raise Forbidden()
    invitee = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if invitee is not None:
        if is_platform_admin(invitee):
            raise ValidationFailed.field("email", "Platform admin accounts can't join a college.")
        already = db.execute(
            select(CollegeMembership.id).where(
                CollegeMembership.college_id == campus.college_id,
                CollegeMembership.user_id == invitee.id,
                CollegeMembership.status == MembershipStatus.ACTIVE,
            )
        ).first()
        if already is not None:
            raise Conflict(
                "This person is already a member of your college.", code="already_member"
            )
    invite, token = create_invite(
        db,
        college=campus.college,
        email=email,
        kind=kind,
        grants=[],
        invited_by=campus.user,
        now=now,
    )
    record_audit(
        db,
        action=ACTION_INVITE_SENT,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="invite",
        target_id=str(invite.id),
        metadata={"kind": kind},
    )
    db.commit()
    return invite, invite_email(settings, campus.college, email, token, admin=False)


def pending_invites(db: Session, campus: CampusContext, now: datetime) -> list[Invite]:
    if not can_manage_college(campus):
        raise Forbidden()
    return list(
        db.execute(
            select(Invite)
            .where(
                Invite.college_id == campus.college_id,
                Invite.accepted_at.is_(None),
                Invite.revoked_at.is_(None),
                Invite.expires_at > now,
            )
            .order_by(Invite.created_at.desc(), Invite.id.desc())
            .limit(200)
        ).scalars()
    )
