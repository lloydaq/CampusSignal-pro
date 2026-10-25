"""Campus issue routes (architecture.md §11.1). The college comes from `Campus`; the service
loads the issue inside it and applies app/policies/issues.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import MAX_LIMIT, decode_ranked_cursor
from app.models import IssueCategory, IssueStatus
from app.schemas.issues import (
    DuplicateOf,
    IssueCreate,
    IssueDetail,
    IssuePage,
    IssueSummary,
    IssueUpdateOut,
)
from app.services.issues import service as issues
from app.services.issues.service import IssueDetailView, IssueScope, IssueView

router = APIRouter(prefix="/campus/issues", tags=["issues"], dependencies=[Depends(no_store)])

ISSUE_PAGE_SIZE = 20
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]


def _summary(view: IssueView) -> IssueSummary:
    issue = view.issue
    return IssueSummary(
        id=issue.id,
        title=issue.title,
        category=issue.category,
        location=issue.location_text,
        room=issue.room,
        status=issue.status,
        reporter_name=view.reporter_name,
        assignee_name=view.assignee_name,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


def _detail(view: IssueDetailView) -> IssueDetail:
    issue = view.issue
    duplicate = view.duplicate_of
    return IssueDetail(
        **_summary(view).model_dump(),
        description=issue.description,
        resolved_at=issue.resolved_at,
        version=issue.version,
        # ISSUE-006: the original's status and resolution time, and its id only for someone
        # who may open it.
        duplicate_of=DuplicateOf(
            id=duplicate.original.id if duplicate.readable else None,
            status=duplicate.original.status,
            resolved_at=duplicate.original.resolved_at,
        )
        if duplicate
        else None,
        updates=[
            IssueUpdateOut(
                id=u.update.id,
                kind=u.update.kind,
                from_status=u.update.from_status,
                to_status=u.update.to_status,
                body=u.update.body,
                is_internal=u.update.is_internal,
                actor_name=u.actor_name,
                created_at=u.update.created_at,
            )
            for u in view.updates
        ],
    )


@router.get("")
def list_issues(
    campus: Campus,
    db: Db,
    now: Now,
    scope: IssueScope = IssueScope.MINE,
    status: IssueStatus | None = None,
    category: IssueCategory | None = None,
    assignee_id: uuid.UUID | None = None,
    older_than_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    cursor: CursorParam = None,
    limit: Limit = ISSUE_PAGE_SIZE,
) -> IssuePage:
    views, next_cursor = issues.list_issues(
        db,
        campus,
        scope=scope,
        status=status,
        category=category,
        assignee_id=assignee_id,
        older_than_days=older_than_days,
        cursor=decode_ranked_cursor(cursor),
        limit=limit,
        now=now,
    )
    return IssuePage(items=[_summary(v) for v in views], next_cursor=next_cursor)


@router.post("", status_code=201)
def create_issue(body: IssueCreate, campus: Campus, db: Db, now: Now) -> IssueDetail:
    view = issues.create_issue(
        db,
        campus,
        category=body.category,
        title=body.title,
        description=body.description,
        location=body.location,
        room=body.room,
        now=now,
    )
    return _detail(view)


@router.get("/{issue_id}")
def get_issue(issue_id: uuid.UUID, campus: Campus, db: Db) -> IssueDetail:
    return _detail(issues.get_issue(db, campus, issue_id))
