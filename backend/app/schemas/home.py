"""The role-aware home (HOME-001…004). Each block is present only for viewers it's meant for;
`status` "error" means that block failed and the rest are still good (US-16)."""

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel

from app.schemas.academic import MyAttendanceItem, SectionRef, SubjectRef, TermRef

Status = Literal["ok", "error"]


class HomeClass(BaseModel):
    starts_at: time
    ends_at: time
    room: str
    section: SectionRef
    subject: SubjectRef


class ClassesBlock(BaseModel):
    """Today's classes: a student's own, or a faculty member's sections'."""

    status: Status
    term: TermRef | None = None
    items: list[HomeClass] = []


class AttendanceBlock(BaseModel):
    status: Status
    term: TermRef | None = None
    items: list[MyAttendanceItem] = []


class MissingAttendance(BaseModel):
    section: SectionRef
    subject: SubjectRef
    held_on: date
    starts_at: time


class NeedsAttendanceBlock(BaseModel):
    """HOME-002: timetabled classes in the last 7 days with no attendance recorded."""

    status: Status
    items: list[MissingAttendance] = []


class HomeIssue(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    created_at: datetime


class MyIssuesBlock(BaseModel):
    status: Status
    open_count: int = 0
    items: list[HomeIssue] = []


class QueueCount(BaseModel):
    kind: Literal["membership_requests", "content_reports", "unacknowledged_issues"]
    count: int


class QueuesBlock(BaseModel):
    """HOME-003: only the queues the viewer can act on."""

    status: Status
    items: list[QueueCount] = []


class HomeOut(BaseModel):
    today: date
    is_demo: bool
    classes: ClassesBlock | None = None
    attendance: AttendanceBlock | None = None
    needs_attendance: NeedsAttendanceBlock | None = None
    my_issues: MyIssuesBlock
    queues: QueuesBlock | None = None
