"""Community decisions (COMMUNITY-001, 002, 005, 006, 007). Pure functions over loaded rows.

Who reads a post: anyone in the college for a COLLEGE post; for a DEPARTMENT post, that
department's members, its department admins and college admins (the same audience as a
department notice). Deleted posts reach nobody; hidden ones only their author and moderators.
Feeds filter in SQL with `feed_audience` and `sees_hidden_in_feed`; a test keeps them in
agreement with `can_read_post`, so a feed never shows what the single-post route refuses.
"""

import uuid

from app.models import Comment, ContentStatus, Post, PostVisibility
from app.policies.campus import CampusContext, administered_departments, is_college_admin
from app.policies.notices import DepartmentAudience, ManagedAudience, published_audience


def feed_audience(campus: CampusContext) -> DepartmentAudience:
    """Whose department posts this member may read (COMMUNITY-002)."""
    return published_audience(campus)


def is_post_author(campus: CampusContext, post: Post) -> bool:
    return post.author_membership_id == campus.membership.id


def can_moderate_post(campus: CampusContext, post: Post) -> bool:
    """COMMUNITY-007: college admins moderate everything; a department admin only their
    departments' posts, never a college post."""
    if is_college_admin(campus.grants):
        return True
    return (
        post.visibility == PostVisibility.DEPARTMENT
        and post.department_id is not None
        and post.department_id in administered_departments(campus.grants)
    )


def sees_hidden_in_feed(campus: CampusContext, department_id: uuid.UUID | None) -> bool:
    """Whether a feed shows its hidden posts to this member: only to whoever moderates every
    post in it (the college feed: college admins; a department feed: also its admins)."""
    if is_college_admin(campus.grants):
        return True
    return department_id is not None and department_id in administered_departments(campus.grants)


def can_read_post(campus: CampusContext, post: Post) -> bool:
    if post.deleted_at is not None:
        return False
    if post.visibility == PostVisibility.DEPARTMENT and not (
        post.department_id is not None and feed_audience(campus).includes(post.department_id)
    ):
        return False
    if post.status == ContentStatus.HIDDEN:
        return is_post_author(campus, post) or can_moderate_post(campus, post)
    return True


def can_post_with(campus: CampusContext, visibility: PostVisibility) -> bool:
    """COMMUNITY-001: to the whole college, or to the poster's own home department only."""
    if visibility == PostVisibility.COLLEGE:
        return True
    return campus.membership.department_id is not None


def can_edit_post(campus: CampusContext, post: Post) -> bool:
    """COMMUNITY-005: the author, while the post is visible (a hidden post stays as it was)."""
    return (
        can_read_post(campus, post)
        and is_post_author(campus, post)
        and post.status == ContentStatus.VISIBLE
    )


def can_delete_post(campus: CampusContext, post: Post) -> bool:
    return can_read_post(campus, post) and is_post_author(campus, post)


def can_engage_post(campus: CampusContext, post: Post) -> bool:
    """Comment on or react to: a visible post the member can read. A hidden post is frozen
    (owner, 2026-10-31)."""
    return can_read_post(campus, post) and post.status == ContentStatus.VISIBLE


def can_read_comment(campus: CampusContext, post: Post, comment: Comment) -> bool:
    if not can_read_post(campus, post) or comment.deleted_at is not None:
        return False
    if comment.status == ContentStatus.HIDDEN:
        return comment.author_membership_id == campus.membership.id or can_moderate_post(
            campus, post
        )
    return True


def can_edit_comment(campus: CampusContext, post: Post, comment: Comment) -> bool:
    return (
        can_read_comment(campus, post, comment)
        and comment.author_membership_id == campus.membership.id
        and comment.status == ContentStatus.VISIBLE
        and post.status == ContentStatus.VISIBLE
    )


def can_delete_comment(campus: CampusContext, post: Post, comment: Comment) -> bool:
    return (
        can_read_comment(campus, post, comment)
        and comment.author_membership_id == campus.membership.id
    )


def can_report(campus: CampusContext, post: Post, comment: Comment | None) -> bool:
    """COMMUNITY-006: any member, about visible content they can read that isn't their own.
    Hidden content has already been dealt with."""
    if not can_read_post(campus, post) or post.status != ContentStatus.VISIBLE:
        return False
    if comment is None:
        return not is_post_author(campus, post)
    return (
        can_read_comment(campus, post, comment)
        and comment.status == ContentStatus.VISIBLE
        and comment.author_membership_id != campus.membership.id
    )


def can_see_moderation_queue(campus: CampusContext) -> bool:
    """COMMUNITY-007: college admins and department admins."""
    return is_college_admin(campus.grants) or bool(administered_departments(campus.grants))


def moderation_audience(campus: CampusContext) -> ManagedAudience:
    """The reports a moderator sees, in SQL terms: those about college posts (college admins
    only) and about these departments' posts. Matches `can_moderate_post` (a test checks)."""
    if is_college_admin(campus.grants):
        return ManagedAudience(True, DepartmentAudience(True))
    return ManagedAudience(
        False, DepartmentAudience(False, administered_departments(campus.grants))
    )
