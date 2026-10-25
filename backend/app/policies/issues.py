"""Campus issue decisions (ISSUE-003, 004, 005). Pure functions over loaded rows.

What someone is to an issue is a set of actors (app/services/issues/state_machine.py): its
reporter, its current assignee, an issue coordinator, a college admin. Reading needs any of them;
the transition table decides changes. Lists filter in SQL by the same facts (reporter = me,
assignee = me, or the whole college for the queue), so a list never shows an issue the
single-issue route would refuse.
"""

from app.models import CampusIssue, IssueStatus, Role
from app.policies.campus import CampusContext, is_college_admin
from app.services.issues.state_machine import Actor


def is_issue_coordinator(campus: CampusContext) -> bool:
    return any(g.role == Role.ISSUE_COORDINATOR for g in campus.grants)


def issue_actors(campus: CampusContext, issue: CampusIssue) -> frozenset[Actor]:
    actors: set[Actor] = set()
    if issue.reporter_membership_id == campus.membership.id:
        actors.add(Actor.REPORTER)
    if issue.assignee_membership_id is not None and (
        issue.assignee_membership_id == campus.membership.id
    ):
        actors.add(Actor.ASSIGNEE)
    if is_issue_coordinator(campus):
        actors.add(Actor.COORDINATOR)
    if is_college_admin(campus.grants):
        actors.add(Actor.COLLEGE_ADMIN)
    return frozenset(actors)


def can_read_issue(campus: CampusContext, issue: CampusIssue) -> bool:
    """ISSUE-003: the reporter, the current assignee, coordinators and college admins. Other
    members (students included) don't see the issue at all."""
    return bool(issue_actors(campus, issue))


def can_see_queue(campus: CampusContext) -> bool:
    """The coordinator queue: every issue in the college."""
    return is_issue_coordinator(campus) or is_college_admin(campus.grants)


def can_assign_issues(campus: CampusContext) -> bool:
    """ISSUE-004: coordinators assign; college admins hold every issue power too."""
    return can_see_queue(campus)


def can_see_internal_updates(campus: CampusContext, issue: CampusIssue) -> bool:
    """ISSUE-005: internal updates are for the handling side, never the reporter as such."""
    return bool(issue_actors(campus, issue) - {Actor.REPORTER})


def can_comment_issue(campus: CampusContext, issue: CampusIssue, *, internal: bool) -> bool:
    """ISSUE-005: the handling side comments publicly or internally; the reporter publicly,
    while the issue isn't REJECTED."""
    if can_see_internal_updates(campus, issue):
        return True
    reporter = Actor.REPORTER in issue_actors(campus, issue)
    return reporter and not internal and issue.status != IssueStatus.REJECTED
