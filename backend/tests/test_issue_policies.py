"""Issue policies as pure functions (ISSUE-003, 004, 005): no database, objects in memory."""

import uuid

import pytest

from app.models import (
    CampusIssue,
    College,
    CollegeMembership,
    IssueStatus,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.policies.issues import (
    can_assign_issues,
    can_comment_issue,
    can_read_issue,
    can_see_internal_updates,
    can_see_queue,
    issue_actors,
)
from app.services.issues.state_machine import Actor

ME = uuid.uuid4()
SOMEONE = uuid.uuid4()


def ctx(*roles: Role, kind: MembershipKind = MembershipKind.STUDENT) -> CampusContext:
    return CampusContext(
        user=User(email="a@northfield.example", password_hash="x", display_name="A"),
        membership=CollegeMembership(id=ME, kind=kind, status=MembershipStatus.ACTIVE),
        college=College(name="Northfield Institute", slug="northfield", timezone="UTC"),
        grants=tuple(RoleGrant(role=r) for r in roles),
    )


def issue(
    reporter: uuid.UUID = SOMEONE,
    assignee: uuid.UUID | None = None,
    status: IssueStatus = IssueStatus.SUBMITTED,
) -> CampusIssue:
    return CampusIssue(
        reporter_membership_id=reporter, assignee_membership_id=assignee, status=status
    )


class TestActors:
    def test_a_stranger_is_nobody(self) -> None:
        assert issue_actors(ctx(), issue()) == frozenset()

    def test_reporter_and_assignee_come_from_the_issue(self) -> None:
        assert issue_actors(ctx(), issue(reporter=ME)) == {Actor.REPORTER}
        assert issue_actors(ctx(kind=MembershipKind.STAFF), issue(assignee=ME)) == {Actor.ASSIGNEE}

    def test_roles_come_from_grants(self) -> None:
        assert issue_actors(ctx(Role.ISSUE_COORDINATOR), issue()) == {Actor.COORDINATOR}
        assert issue_actors(ctx(Role.COLLEGE_ADMIN), issue()) == {Actor.COLLEGE_ADMIN}

    def test_a_department_admin_has_no_issue_powers(self) -> None:
        assert issue_actors(ctx(Role.DEPARTMENT_ADMIN), issue()) == frozenset()

    def test_one_person_can_be_several(self) -> None:
        actors = issue_actors(ctx(Role.ISSUE_COORDINATOR), issue(reporter=ME, assignee=ME))
        assert actors == {Actor.REPORTER, Actor.ASSIGNEE, Actor.COORDINATOR}


class TestReading:  # ISSUE-003
    @pytest.mark.parametrize(
        ("campus", "subject", "allowed"),
        [
            (ctx(), issue(reporter=ME), True),
            (ctx(), issue(), False),  # another student's issue
            (ctx(kind=MembershipKind.FACULTY), issue(), False),
            (ctx(Role.DEPARTMENT_ADMIN), issue(), False),
            (ctx(kind=MembershipKind.STAFF), issue(assignee=ME), True),
            (ctx(Role.ISSUE_COORDINATOR), issue(), True),
            (ctx(Role.COLLEGE_ADMIN), issue(), True),
        ],
    )
    def test_who_reads_an_issue(
        self, campus: CampusContext, subject: CampusIssue, allowed: bool
    ) -> None:
        assert can_read_issue(campus, subject) is allowed

    def test_a_former_assignee_loses_access(self) -> None:
        assert not can_read_issue(ctx(kind=MembershipKind.STAFF), issue(assignee=SOMEONE))

    @pytest.mark.parametrize(
        ("campus", "allowed"),
        [
            (ctx(), False),
            (ctx(kind=MembershipKind.FACULTY), False),
            (ctx(Role.DEPARTMENT_ADMIN), False),
            (ctx(Role.ISSUE_COORDINATOR), True),
            (ctx(Role.COLLEGE_ADMIN), True),
        ],
    )
    def test_who_sees_the_queue_and_assigns(self, campus: CampusContext, allowed: bool) -> None:
        assert can_see_queue(campus) is allowed
        assert can_assign_issues(campus) is allowed


class TestInternalUpdates:  # ISSUE-005
    def test_the_reporter_never_sees_internal_updates(self) -> None:
        assert not can_see_internal_updates(ctx(), issue(reporter=ME))

    @pytest.mark.parametrize(
        ("campus", "subject"),
        [
            (ctx(kind=MembershipKind.STAFF), issue(assignee=ME)),
            (ctx(Role.ISSUE_COORDINATOR), issue()),
            (ctx(Role.COLLEGE_ADMIN), issue()),
            # A coordinator who reported the issue is still a coordinator.
            (ctx(Role.ISSUE_COORDINATOR), issue(reporter=ME)),
        ],
    )
    def test_the_handling_side_does(self, campus: CampusContext, subject: CampusIssue) -> None:
        assert can_see_internal_updates(campus, subject)


class TestComments:  # ISSUE-005
    def test_the_reporter_comments_publicly_until_rejected(self) -> None:
        for status in IssueStatus:
            subject = issue(reporter=ME, status=status)
            assert can_comment_issue(ctx(), subject, internal=False) is (
                status != IssueStatus.REJECTED
            )
            assert not can_comment_issue(ctx(), subject, internal=True)

    @pytest.mark.parametrize(
        ("campus", "subject"),
        [
            (ctx(kind=MembershipKind.STAFF), issue(assignee=ME)),
            (ctx(Role.ISSUE_COORDINATOR), issue()),
            (ctx(Role.COLLEGE_ADMIN), issue()),
        ],
    )
    def test_the_handling_side_comments_either_way(
        self, campus: CampusContext, subject: CampusIssue
    ) -> None:
        for status in IssueStatus:
            subject.status = status
            assert can_comment_issue(campus, subject, internal=False)
            assert can_comment_issue(campus, subject, internal=True)

    def test_strangers_never_comment(self) -> None:
        assert not can_comment_issue(ctx(), issue(), internal=False)
