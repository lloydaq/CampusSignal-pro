"""The role-aware home (HOME-001…004; architecture.md §11.1 `GET /campus/home`). Composed by
app/services/home.py from the module services."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import Campus, Db, Now, no_store
from app.schemas.academic import MyAttendanceItem, SectionRef, SubjectRef, TermRef
from app.schemas.home import (
    AttendanceBlock,
    ClassesBlock,
    HomeClass,
    HomeIssue,
    HomeOut,
    MissingAttendance,
    MyIssuesBlock,
    NeedsAttendanceBlock,
    QueueCount,
    QueuesBlock,
)
from app.services import home as service

router = APIRouter(prefix="/campus", tags=["home"], dependencies=[Depends(no_store)])


def _term(data: dict[str, Any]) -> TermRef | None:
    return TermRef.from_term(data["term"]) if data.get("term") else None


def _classes(block: service.Block) -> ClassesBlock:
    if not block.ok:
        return ClassesBlock(status="error")
    return ClassesBlock(
        status="ok",
        term=_term(block.data),
        items=[
            HomeClass(
                starts_at=r.entry.starts_at,
                ends_at=r.entry.ends_at,
                room=r.entry.room,
                section=SectionRef(id=r.section.id, name=r.section.name),
                subject=SubjectRef.from_subject(r.subject),
            )
            for r in block.data["items"]
        ],
    )


def _attendance(block: service.Block) -> AttendanceBlock:
    if not block.ok:
        return AttendanceBlock(status="error")
    return AttendanceBlock(
        status="ok",
        term=_term(block.data),
        items=[
            MyAttendanceItem(
                section=SectionRef(id=r.section.id, name=r.section.name),
                subject=SubjectRef.from_subject(r.subject),
                held=r.summary.held,
                attended=r.summary.attended,
                excused=r.summary.excused,
                percentage=r.summary.percentage,
            )
            for r in block.data["items"]
        ],
    )


def _needs(block: service.Block) -> NeedsAttendanceBlock:
    if not block.ok:
        return NeedsAttendanceBlock(status="error")
    return NeedsAttendanceBlock(
        status="ok",
        items=[
            MissingAttendance(
                section=SectionRef(id=m.section.id, name=m.section.name),
                subject=SubjectRef.from_subject(m.subject),
                held_on=m.held_on,
                starts_at=m.starts_at,
            )
            for m in block.data["items"]
        ],
    )


def _issues(block: service.Block) -> MyIssuesBlock:
    if not block.ok:
        return MyIssuesBlock(status="error")
    return MyIssuesBlock(
        status="ok",
        open_count=block.data["open_count"],
        items=[
            HomeIssue(
                id=v.issue.id,
                title=v.issue.title,
                status=v.issue.status,
                created_at=v.issue.created_at,
            )
            for v in block.data["items"]
        ],
    )


def _queues(block: service.Block) -> QueuesBlock:
    if not block.ok:
        return QueuesBlock(status="error")
    return QueuesBlock(
        status="ok", items=[QueueCount(kind=k, count=c) for k, c in block.data["items"]]
    )


@router.get("/home")
def home(campus: Campus, db: Db, now: Now) -> HomeOut:
    blocks = service.home(db, campus, now)
    return HomeOut(
        today=service.college_now(campus, now).date(),
        is_demo=campus.college.is_demo,
        classes=_classes(blocks["classes"]) if "classes" in blocks else None,
        attendance=_attendance(blocks["attendance"]) if "attendance" in blocks else None,
        needs_attendance=_needs(blocks["needs_attendance"])
        if "needs_attendance" in blocks
        else None,
        my_issues=_issues(blocks["my_issues"]),
        queues=_queues(blocks["queues"]) if "queues" in blocks else None,
    )
