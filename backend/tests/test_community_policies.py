"""Community policies as pure functions (COMMUNITY-001, 002, 005, 007): no database."""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import (
    College,
    CollegeMembership,
    Comment,
    ContentStatus,
    MembershipKind,
    MembershipStatus,
    Post,
    PostVisibility,
    Role,
    RoleGrant,
)
from app.models.user import User
from app.policies.campus import CampusContext
from app.policies.community import (
    can_delete_comment,
    can_delete_post,
    can_edit_comment,
    can_edit_post,
    can_engage_post,
    can_moderate_post,
    can_post_with,
    can_read_comment,
    can_read_post,
    feed_audience,
    sees_hidden_in_feed,
)

CSE = uuid.uuid4()
MECH = uuid.uuid4()
ME = uuid.uuid4()
SOMEONE = uuid.uuid4()
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def ctx(
    *roles: tuple[Role, uuid.UUID | None],
    department: uuid.UUID | None = CSE,
    kind: MembershipKind = MembershipKind.STUDENT,
) -> CampusContext:
    return CampusContext(
        user=User(email="a@northfield.example", password_hash="x", display_name="A"),
        membership=CollegeMembership(
            id=ME, kind=kind, status=MembershipStatus.ACTIVE, department_id=department
        ),
        college=College(name="Northfield Institute", slug="northfield", timezone="UTC"),
        grants=tuple(RoleGrant(role=r, department_id=d) for r, d in roles),
    )


def post(
    visibility: PostVisibility = PostVisibility.COLLEGE,
    department: uuid.UUID | None = None,
    author: uuid.UUID = SOMEONE,
    status: ContentStatus = ContentStatus.VISIBLE,
    deleted: bool = False,
) -> Post:
    return Post(
        visibility=visibility,
        department_id=department,
        author_membership_id=author,
        status=status,
        deleted_at=NOW if deleted else None,
    )


def dept_post(department: uuid.UUID = CSE, **kw: object) -> Post:
    return post(PostVisibility.DEPARTMENT, department, **kw)  # type: ignore[arg-type]


COLLEGE_ADMIN = (Role.COLLEGE_ADMIN, None)
MECH_ADMIN = (Role.DEPARTMENT_ADMIN, MECH)


class TestReading:  # COMMUNITY-002, US-10
    def test_college_posts_reach_every_member(self) -> None:
        assert can_read_post(ctx(), post())
        assert can_read_post(ctx(department=None, kind=MembershipKind.STAFF), post())

    @pytest.mark.parametrize(
        ("campus", "allowed"),
        [
            (ctx(), True),  # a CSE member
            (ctx(department=MECH), False),  # another department (US-10)
            (ctx(department=None, kind=MembershipKind.STAFF), False),
            (ctx(MECH_ADMIN, department=None), False),  # admin of another department
            (ctx((Role.DEPARTMENT_ADMIN, CSE), department=None), True),
            (ctx(COLLEGE_ADMIN, department=MECH), True),
            (ctx((Role.ISSUE_COORDINATOR, None), department=MECH), False),
        ],
    )
    def test_department_posts_reach_their_department(
        self, campus: CampusContext, allowed: bool
    ) -> None:
        assert can_read_post(campus, dept_post()) is allowed

    def test_deleted_posts_reach_nobody(self) -> None:
        for campus in (ctx(), ctx(COLLEGE_ADMIN)):
            assert not can_read_post(campus, post(deleted=True, author=ME))

    def test_hidden_posts_reach_only_the_author_and_moderators(self) -> None:
        hidden = dept_post(status=ContentStatus.HIDDEN)
        assert not can_read_post(ctx(), hidden)
        assert can_read_post(ctx(), dept_post(status=ContentStatus.HIDDEN, author=ME))
        assert can_read_post(ctx((Role.DEPARTMENT_ADMIN, CSE), department=None), hidden)
        assert can_read_post(ctx(COLLEGE_ADMIN), hidden)

    def test_the_feed_audience_matches_single_reads(self) -> None:
        campuses = [
            ctx(),
            ctx(department=MECH),
            ctx(department=None, kind=MembershipKind.STAFF),
            ctx(MECH_ADMIN),
            ctx(COLLEGE_ADMIN, department=None),
        ]
        for campus in campuses:
            audience = feed_audience(campus)
            for department in (CSE, MECH):
                assert audience.includes(department) is can_read_post(campus, dept_post(department))


class TestModeration:  # COMMUNITY-007, US-10
    def test_college_admins_moderate_everything(self) -> None:
        assert can_moderate_post(ctx(COLLEGE_ADMIN), post())
        assert can_moderate_post(ctx(COLLEGE_ADMIN), dept_post(MECH))

    def test_department_admins_moderate_their_departments_posts_only(self) -> None:
        campus = ctx(MECH_ADMIN)
        assert can_moderate_post(campus, dept_post(MECH))
        assert not can_moderate_post(campus, dept_post(CSE))
        assert not can_moderate_post(campus, post())  # a college post (US-10: 403)

    def test_members_moderate_nothing(self) -> None:
        assert not can_moderate_post(ctx(), dept_post())
        assert not can_moderate_post(ctx(), post(author=ME))

    def test_hidden_posts_show_in_a_feed_only_to_its_moderators(self) -> None:
        assert sees_hidden_in_feed(ctx(COLLEGE_ADMIN), None)
        assert not sees_hidden_in_feed(ctx(MECH_ADMIN), None)
        assert sees_hidden_in_feed(ctx(MECH_ADMIN), MECH)
        assert not sees_hidden_in_feed(ctx(MECH_ADMIN), CSE)
        assert not sees_hidden_in_feed(ctx(), CSE)


class TestWriting:  # COMMUNITY-001, 005
    def test_anyone_posts_to_the_college_and_to_their_own_department(self) -> None:
        assert can_post_with(ctx(), PostVisibility.COLLEGE)
        assert can_post_with(ctx(), PostVisibility.DEPARTMENT)

    def test_without_a_home_department_only_the_college(self) -> None:
        # Even a department admin: posts go to the poster's own department (owner, 2026-10-31).
        campus = ctx(MECH_ADMIN, department=None, kind=MembershipKind.STAFF)
        assert can_post_with(campus, PostVisibility.COLLEGE)
        assert not can_post_with(campus, PostVisibility.DEPARTMENT)

    def test_only_the_author_edits_and_deletes(self) -> None:
        mine, theirs = post(author=ME), post()
        assert can_edit_post(ctx(), mine) and can_delete_post(ctx(), mine)
        assert not can_edit_post(ctx(), theirs) and not can_delete_post(ctx(), theirs)
        # Moderators hide; they don't edit or delete other people's words.
        assert not can_edit_post(ctx(COLLEGE_ADMIN), theirs)
        assert not can_delete_post(ctx(COLLEGE_ADMIN), theirs)

    def test_a_hidden_post_can_be_deleted_by_its_author_but_not_edited(self) -> None:
        hidden = post(author=ME, status=ContentStatus.HIDDEN)
        assert can_delete_post(ctx(), hidden)
        assert not can_edit_post(ctx(), hidden)

    def test_comments_and_reactions_need_a_visible_post_the_member_can_read(self) -> None:
        assert can_engage_post(ctx(), post())
        assert not can_engage_post(ctx(department=MECH), dept_post())
        assert not can_engage_post(ctx(), post(status=ContentStatus.HIDDEN, author=ME))
        assert not can_engage_post(ctx(COLLEGE_ADMIN), post(status=ContentStatus.HIDDEN))
        assert not can_engage_post(ctx(), post(deleted=True))


class TestComments:  # COMMUNITY-003, 005
    def comment(
        self,
        author: uuid.UUID = SOMEONE,
        status: ContentStatus = ContentStatus.VISIBLE,
        deleted: bool = False,
    ) -> Comment:
        return Comment(
            author_membership_id=author, status=status, deleted_at=NOW if deleted else None
        )

    def test_a_comment_is_read_with_its_post(self) -> None:
        assert can_read_comment(ctx(), post(), self.comment())
        assert not can_read_comment(ctx(department=MECH), dept_post(), self.comment())
        assert not can_read_comment(ctx(), post(), self.comment(deleted=True))

    def test_hidden_comments_reach_their_author_and_the_posts_moderators(self) -> None:
        hidden = self.comment(status=ContentStatus.HIDDEN)
        assert not can_read_comment(ctx(), post(), hidden)
        assert can_read_comment(ctx(), post(), self.comment(ME, ContentStatus.HIDDEN))
        assert can_read_comment(ctx(MECH_ADMIN), dept_post(MECH), hidden)
        assert not can_read_comment(ctx(MECH_ADMIN), post(), hidden)

    def test_only_the_author_edits_or_deletes_a_comment(self) -> None:
        assert can_edit_comment(ctx(), post(), self.comment(ME))
        assert can_delete_comment(ctx(), post(), self.comment(ME))
        assert not can_edit_comment(ctx(), post(), self.comment())
        assert not can_delete_comment(ctx(COLLEGE_ADMIN), post(), self.comment())
        # Once the post is hidden, its comments are frozen (owner, 2026-10-31).
        assert not can_edit_comment(ctx(), post(status=ContentStatus.HIDDEN), self.comment(ME))


class TestReports:  # COMMUNITY-006, 007
    def test_members_report_what_they_can_read_but_not_their_own(self) -> None:
        from app.policies.community import can_report

        assert can_report(ctx(), post(), None)
        assert not can_report(ctx(), post(author=ME), None)
        assert not can_report(ctx(department=MECH), dept_post(), None)  # can't read it
        assert not can_report(ctx(), post(deleted=True), None)
        comment = Comment(author_membership_id=SOMEONE, status=ContentStatus.VISIBLE)
        assert can_report(ctx(), post(author=ME), comment)  # someone else's comment on mine
        own = Comment(author_membership_id=ME, status=ContentStatus.VISIBLE)
        assert not can_report(ctx(), post(), own)

    def test_hidden_content_is_already_handled(self) -> None:
        from app.policies.community import can_report

        assert not can_report(ctx(COLLEGE_ADMIN), post(status=ContentStatus.HIDDEN), None)
        hidden = Comment(author_membership_id=SOMEONE, status=ContentStatus.HIDDEN)
        assert not can_report(ctx(COLLEGE_ADMIN), post(), hidden)

    @pytest.mark.parametrize(
        ("campus", "allowed"),
        [
            (ctx(), False),
            (ctx(kind=MembershipKind.FACULTY), False),
            (ctx((Role.ISSUE_COORDINATOR, None)), False),
            (ctx(MECH_ADMIN), True),
            (ctx(COLLEGE_ADMIN), True),
        ],
    )
    def test_the_queue_is_for_moderators(self, campus: CampusContext, allowed: bool) -> None:
        from app.policies.community import can_see_moderation_queue

        assert can_see_moderation_queue(campus) is allowed

    def test_the_queue_audience_matches_moderation_rights(self) -> None:
        from app.policies.community import moderation_audience

        for campus in (ctx(), ctx(MECH_ADMIN), ctx(COLLEGE_ADMIN)):
            audience = moderation_audience(campus)
            for target in (post(), dept_post(CSE), dept_post(MECH)):
                in_queue = (
                    audience.include_college
                    if target.visibility == PostVisibility.COLLEGE
                    else target.department_id is not None
                    and audience.departments.includes(target.department_id)
                )
                assert in_queue is can_moderate_post(campus, target)
