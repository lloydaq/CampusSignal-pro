"""Campus issues: handling them (ISSUE-002, 004, 005, 006, 008).

Status changes follow the PRD §9.8.1 table (state_machine.py, through policies/issues.py) on an
issue locked for the change and at the version the person last saw: two coordinators acting at
once can't both win, and nobody changes an issue they haven't seen the latest of (409). Every
change appends a timeline row and, for status changes and assignments, an audit entry; the
reporter hears of status changes and an assignee of being assigned, in the same transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import Cursor, newest_first, split_page
from app.models import (
    CampusIssue,
    CollegeMembership,
    IssueStatus,
    IssueUpdate,
    IssueUpdateKind,
    MembershipKind,
    MembershipStatus,
    User,
)
from app.models.notification import NotificationType
from app.policies.campus import CampusContext
from app.policies.issues import (
    can_assign_issues,
    can_comment_issue,
    is_assignable,
    issue_actors,
    transition_refusal,
)
from app.services import notifications
from app.services.audit import record_audit
from app.services.issues.service import IssueDetailView, get_issue, load_issue
from app.services.issues.state_machine import TransitionProblem, is_reporter_reopen

ACTION_STATUS_CHANGED = "issue.status_changed"
ACTION_ASSIGNED = "issue.assigned"


def _refusal(problem: TransitionProblem) -> AppError:
    match problem:
        case TransitionProblem.NOT_ALLOWED:
            return Forbidden()
        case TransitionProblem.NOTE_REQUIRED:
            return ValidationFailed.field("note", "Add a note to explain this change.")
        case TransitionProblem.REOPEN_WINDOW_CLOSED:
            return Conflict(
                "A resolved issue can be reopened within 14 days. Report it again instead.",
                code=problem,
            )
        case TransitionProblem.REOPEN_LIMIT:
            return Conflict(
                "You've reopened this issue twice already. Report it again instead.", code=problem
            )
        case TransitionProblem.INVALID:
            return Conflict(
                "This issue can't move to that status from where it is now.", code=problem
            )


# What the reporter is told (ISSUE-008); reopens and duplicates get their own words.
_HEADLINES = {
    IssueStatus.ACKNOWLEDGED: "Issue acknowledged",
    IssueStatus.IN_PROGRESS: "Issue in progress",
    IssueStatus.RESOLVED: "Issue resolved",
    IssueStatus.REJECTED: "Issue closed without action",
}


def _check_version(issue: CampusIssue, version: int) -> None:
    if issue.version != version:
        raise Conflict(
            "This issue was changed by someone else. Reload and try again.",
            code="version_conflict",
        )


def _membership(
    db: Session, campus: CampusContext, membership_id: uuid.UUID
) -> CollegeMembership | None:
    return db.execute(
        select(CollegeMembership).where(
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.id == membership_id,
        )
    ).scalar_one_or_none()


def _tell(
    db: Session,
    campus: CampusContext,
    issue: CampusIssue,
    membership_id: uuid.UUID,
    kind: NotificationType,
    headline: str,
    now: datetime,
) -> None:
    """Notify a member about the issue, unless they made the change themselves or are no
    longer an ACTIVE member (suspended members aren't told, as with notices)."""
    if membership_id == campus.membership.id:
        return
    member = _membership(db, campus, membership_id)
    if member is None or member.status != MembershipStatus.ACTIVE:
        return
    notifications.notify_issue(
        db,
        user_id=member.user_id,
        college_id=campus.college_id,
        issue_id=issue.id,
        kind=kind,
        title=f"{headline}: {issue.title}",
        now=now,
    )


def _original(
    db: Session, campus: CampusContext, issue: CampusIssue, original_id: uuid.UUID
) -> CampusIssue:
    """The issue a duplicate points at (ISSUE-006): one this person may open, in this college,
    and not itself a duplicate, so links never form a chain or a loop."""
    if original_id == issue.id:
        raise ValidationFailed.field("duplicate_of_id", "An issue can't duplicate itself.")
    original = load_issue(db, campus, original_id)
    if original.duplicate_of_id is not None:
        raise ValidationFailed.field(
            "duplicate_of_id", "That issue is itself a duplicate. Link to its original instead."
        )
    return original


# --- status changes (ISSUE-002, 006) ---------------------------------------------------------


def transition_issue(
    db: Session,
    campus: CampusContext,
    issue_id: uuid.UUID,
    *,
    to_status: IssueStatus,
    note: str | None,
    duplicate_of_id: uuid.UUID | None,
    version: int,
    now: datetime,
) -> IssueDetailView:
    issue = load_issue(db, campus, issue_id, lock=True)
    _check_version(issue, version)
    # Marking a duplicate is a rejection whose reason is the link (PRD §9.8.1).
    problem = transition_refusal(
        campus,
        issue,
        to_status,
        note_given=note is not None or duplicate_of_id is not None,
        now=now,
    )
    if problem is not None:
        raise _refusal(problem)
    original = _original(db, campus, issue, duplicate_of_id) if duplicate_of_id else None

    from_status = IssueStatus(issue.status)
    if is_reporter_reopen(from_status, to_status, issue_actors(campus, issue)):
        issue.reporter_reopen_count += 1
    issue.status = to_status
    issue.resolved_at = now if to_status == IssueStatus.RESOLVED else None
    # Reopening a duplicate clears its link (owner, 2026-10-25).
    issue.duplicate_of_id = original.id if original is not None else None
    issue.version += 1
    issue.updated_at = now
    db.add(
        IssueUpdate(
            college_id=campus.college_id,
            issue_id=issue.id,
            actor_membership_id=campus.membership.id,
            kind=IssueUpdateKind.STATUS,
            from_status=from_status,
            to_status=to_status,
            body=note,
            created_at=now,
        )
    )
    reopened = from_status in (IssueStatus.RESOLVED, IssueStatus.REJECTED)
    if original is not None:
        headline = "Issue closed as a duplicate"
    else:
        headline = "Issue reopened" if reopened else _HEADLINES[to_status]
    metadata: dict[str, str] = {"from": from_status, "to": to_status}
    if original is not None:
        metadata["duplicate_of"] = str(original.id)
    record_audit(
        db,
        action=ACTION_STATUS_CHANGED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="issue",
        target_id=str(issue.id),
        # A rejection's or reopen's reason is part of the record (US-14); a resolution note
        # and the report itself are not.
        reason=note if to_status == IssueStatus.REJECTED or reopened else None,
        metadata=metadata,
    )
    _tell(
        db,
        campus,
        issue,
        issue.reporter_membership_id,
        NotificationType.ISSUE_STATUS_CHANGED,
        headline,
        now,
    )
    db.commit()
    return get_issue(db, campus, issue.id, now)


# --- assignment (ISSUE-004) ------------------------------------------------------------------


def assign_issue(
    db: Session,
    campus: CampusContext,
    issue_id: uuid.UUID,
    *,
    assignee_id: uuid.UUID | None,
    version: int,
    now: datetime,
) -> IssueDetailView:
    """Assign the issue to an ACTIVE faculty or staff member of this college, or unassign it
    (`assignee_id` None). Someone outside the college doesn't exist here (404)."""
    issue = load_issue(db, campus, issue_id, lock=True)
    if not can_assign_issues(campus):
        raise Forbidden()
    _check_version(issue, version)
    if issue.status in (IssueStatus.RESOLVED, IssueStatus.REJECTED):
        raise Conflict("Reopen this issue before assigning it.", code="issue_closed")
    if assignee_id is not None:
        assignee = _membership(db, campus, assignee_id)
        if assignee is None:
            raise NotFound()
        if not is_assignable(assignee):
            raise ValidationFailed.field(
                "assignee_id", "Issues can be assigned to active faculty and staff only."
            )
    if assignee_id == issue.assignee_membership_id:
        db.commit()  # nothing changes; release the lock
        return get_issue(db, campus, issue.id, now)

    issue.assignee_membership_id = assignee_id
    issue.version += 1
    issue.updated_at = now
    db.add(
        IssueUpdate(
            college_id=campus.college_id,
            issue_id=issue.id,
            actor_membership_id=campus.membership.id,
            kind=IssueUpdateKind.ASSIGNMENT,
            assignee_membership_id=assignee_id,
            created_at=now,
        )
    )
    record_audit(
        db,
        action=ACTION_ASSIGNED,
        actor_user_id=campus.user.id,
        college_id=campus.college_id,
        target_type="issue",
        target_id=str(issue.id),
        metadata={"assignee_membership_id": str(assignee_id) if assignee_id else None},
    )
    if assignee_id is not None:
        _tell(
            db,
            campus,
            issue,
            assignee_id,
            NotificationType.ISSUE_ASSIGNED,
            "Issue assigned to you",
            now,
        )
    db.commit()
    return get_issue(db, campus, issue.id, now)


def list_assignees(
    db: Session,
    campus: CampusContext,
    *,
    query: str | None,
    cursor: Cursor | None,
    limit: int,
) -> tuple[list[tuple[CollegeMembership, User]], str | None]:
    """The assignee picker: ACTIVE faculty and staff of this college, names only."""
    if not can_assign_issues(campus):
        raise Forbidden()
    statement = (
        select(CollegeMembership, User)
        .join(User, User.id == CollegeMembership.user_id)
        .where(
            CollegeMembership.college_id == campus.college_id,
            CollegeMembership.status == MembershipStatus.ACTIVE,
            CollegeMembership.kind.in_((MembershipKind.FACULTY, MembershipKind.STAFF)),
        )
    )
    if query:
        statement = statement.where(User.display_name.icontains(query, autoescape=True))
    rows = db.execute(
        newest_first(statement, CollegeMembership.created_at, CollegeMembership.id, cursor, limit)
    ).all()
    page, next_cursor = split_page(list(rows), limit, lambda r: (r[0].created_at, r[0].id))
    return [(m, u) for m, u in page], next_cursor


# --- comments (ISSUE-005) --------------------------------------------------------------------


def comment_on_issue(
    db: Session,
    campus: CampusContext,
    issue_id: uuid.UUID,
    *,
    body: str,
    internal: bool,
    now: datetime,
) -> IssueDetailView:
    """A comment doesn't change the issue's version: it never conflicts with a status change."""
    issue = load_issue(db, campus, issue_id, lock=True)
    if not can_comment_issue(campus, issue, internal=internal):
        raise Forbidden()
    db.add(
        IssueUpdate(
            college_id=campus.college_id,
            issue_id=issue.id,
            actor_membership_id=campus.membership.id,
            kind=IssueUpdateKind.COMMENT,
            body=body,
            is_internal=internal,
            created_at=now,
        )
    )
    issue.updated_at = now
    db.commit()
    return get_issue(db, campus, issue.id, now)
