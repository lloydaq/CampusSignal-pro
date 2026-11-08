"""Academic setup shapes (ACADEMIC-001…004). Requests never carry `college_id` (unknown fields
are 422); roll numbers appear only where the caller manages the section's department."""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models import AcademicTerm, ClassSection, Subject, TimetableEntry
from app.schemas.campus import DepartmentRef
from app.schemas.college_admin import Code, Name


def _short(limit: int) -> AfterValidator:
    def clean(value: str) -> str:
        value = " ".join(value.split())
        if not 1 <= len(value) <= limit or not value.isprintable():
            raise PydanticCustomError("invalid_text", f"Use 1 to {limit} characters.")
        return value

    return AfterValidator(clean)


TermName = Annotated[str, _short(80)]
SectionName = Annotated[str, _short(40)]
Room = Annotated[str, _short(60)]
Weekday = Annotated[int, Field(ge=1, le=7, description="1 Monday … 7 Sunday")]
MAX_PICKED_MEMBERS = 500


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _dates_in_order(starts_on: date | None, ends_on: date | None) -> None:
    if starts_on is not None and ends_on is not None and starts_on >= ends_on:
        raise PydanticCustomError("dates_out_of_order", "The term must end after it starts.")


def _times_in_order(starts_at: time | None, ends_at: time | None) -> None:
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        raise PydanticCustomError("times_out_of_order", "The class must end after it starts.")


# --- terms ---------------------------------------------------------------------------------


class TermCreate(_Request):
    name: TermName
    starts_on: date
    ends_on: date
    is_current: bool = False

    @model_validator(mode="after")
    def _order(self) -> Self:
        _dates_in_order(self.starts_on, self.ends_on)
        return self


class TermUpdate(_Request):
    name: TermName | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_current: bool | None = None


class TermRef(BaseModel):
    id: uuid.UUID
    name: str
    is_current: bool

    @classmethod
    def from_term(cls, term: AcademicTerm) -> Self:
        return cls(id=term.id, name=term.name, is_current=term.is_current)


class TermOut(TermRef):
    starts_on: date
    ends_on: date

    @classmethod
    def from_term(cls, term: AcademicTerm) -> Self:
        return cls(
            id=term.id,
            name=term.name,
            is_current=term.is_current,
            starts_on=term.starts_on,
            ends_on=term.ends_on,
        )


class TermList(BaseModel):
    items: list[TermOut]


# --- subjects ------------------------------------------------------------------------------


class SubjectCreate(_Request):
    department_id: uuid.UUID
    code: Code
    name: Name


class SubjectUpdate(_Request):
    name: Name


class SubjectRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str

    @classmethod
    def from_subject(cls, subject: Subject) -> Self:
        return cls(id=subject.id, code=subject.code, name=subject.name)


class SubjectOut(SubjectRef):
    department: DepartmentRef


class SubjectPage(BaseModel):
    items: list[SubjectOut]
    next_cursor: str | None


# --- sections ------------------------------------------------------------------------------


class SectionCreate(_Request):
    term_id: uuid.UUID
    subject_id: uuid.UUID
    name: SectionName


class SectionUpdate(_Request):
    name: SectionName


class Person(BaseModel):
    membership_id: uuid.UUID
    display_name: str


class SectionOut(BaseModel):
    id: uuid.UUID
    name: str
    term: TermRef
    subject: SubjectRef
    department: DepartmentRef
    instructors: list[Person]
    enrollment_count: int

    @classmethod
    def build(
        cls,
        section: ClassSection,
        term: AcademicTerm,
        subject: Subject,
        department: DepartmentRef,
        instructors: list[Person],
        enrollment_count: int,
    ) -> Self:
        return cls(
            id=section.id,
            name=section.name,
            term=TermRef.from_term(term),
            subject=SubjectRef.from_subject(subject),
            department=department,
            instructors=instructors,
            enrollment_count=enrollment_count,
        )


class SectionPage(BaseModel):
    items: list[SectionOut]
    next_cursor: str | None


class SectionList(BaseModel):
    items: list[SectionOut]


class InstructorsSet(_Request):
    membership_ids: Annotated[list[uuid.UUID], Field(max_length=10)]


# --- enrollments ---------------------------------------------------------------------------


class EnrollmentImport(_Request):
    csv: Annotated[str, Field(max_length=100_000)]


class EnrollmentAdd(_Request):
    membership_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_PICKED_MEMBERS)]


class EnrollmentsAdded(BaseModel):
    enrolled: int
    already_enrolled: int


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    display_name: str
    roll_number: str | None
    department: DepartmentRef | None


class EnrollmentPage(BaseModel):
    items: list[EnrollmentOut]
    next_cursor: str | None


# --- timetable -----------------------------------------------------------------------------


class TimetableEntryCreate(_Request):
    weekday: Weekday
    starts_at: time
    ends_at: time
    room: Room

    @model_validator(mode="after")
    def _order(self) -> Self:
        _times_in_order(self.starts_at, self.ends_at)
        return self


class TimetableEntryUpdate(_Request):
    weekday: Weekday | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    room: Room | None = None


class TimetableEntryOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    weekday: int
    starts_at: time
    ends_at: time
    room: str

    @classmethod
    def from_entry(cls, entry: TimetableEntry) -> Self:
        return cls(
            id=entry.id,
            section_id=entry.section_id,
            weekday=entry.weekday,
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
            room=entry.room,
        )


class TimetableList(BaseModel):
    items: list[TimetableEntryOut]


class SectionRef(BaseModel):
    id: uuid.UUID
    name: str


class MyClass(BaseModel):
    weekday: int
    starts_at: time
    ends_at: time
    room: str
    section: SectionRef
    subject: SubjectRef


class MyTimetable(BaseModel):
    """The student's week in the current term (ACADEMIC-004). `term` is null when the college
    has no current term; `is_demo` marks synthetic data (Design.md "Demo data")."""

    term: TermRef | None
    is_demo: bool
    classes: list[MyClass]


class TeachingSections(BaseModel):
    term: TermRef | None
    items: list[SectionOut]


# --- attendance (ACADEMIC-005…007) ---------------------------------------------------------

Status = Literal["PRESENT", "ABSENT", "EXCUSED"]
Slot = Annotated[int, Field(ge=1, le=12, description="The period of the day, 1-12")]
MAX_MARKS = 1000


class AttendanceMark(_Request):
    enrollment_id: uuid.UUID
    status: Status


Marks = Annotated[list[AttendanceMark], Field(min_length=1, max_length=MAX_MARKS)]


class AttendanceSessionCreate(_Request):
    held_on: date
    slot: Slot
    records: Marks


class AttendanceSessionEdit(_Request):
    version: Annotated[int, Field(ge=1)]
    records: Marks
    reason: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class AttendanceCounts(BaseModel):
    present: int
    absent: int
    excused: int


class AttendanceSessionOut(BaseModel):
    """`edit` says how the caller may change it now: "faculty" (inside the window), "correction"
    (department admin, reason required), "window_closed", or null (read only)."""

    id: uuid.UUID
    section_id: uuid.UUID
    held_on: date
    slot: int
    version: int
    recorded_by: Person
    counts: AttendanceCounts
    edit: Literal["faculty", "correction", "window_closed"] | None
    edit_window_closes_at: datetime
    created_at: datetime
    updated_at: datetime


class AttendanceRecordOut(BaseModel):
    enrollment_id: uuid.UUID
    membership_id: uuid.UUID
    display_name: str
    status: str


class AttendanceSessionDetail(AttendanceSessionOut):
    records: list[AttendanceRecordOut]


class AttendanceSessionPage(BaseModel):
    items: list[AttendanceSessionOut]
    next_cursor: str | None


class AttendanceSummary(BaseModel):
    """Held counts sessions with a record for the student; EXCUSED ones leave the
    percentage's denominator (ACADEMIC-007). `percentage` is null until something counts."""

    held: int
    attended: int
    excused: int
    percentage: float | None


class MyAttendanceItem(AttendanceSummary):
    section: SectionRef
    subject: SubjectRef


class MyAttendance(BaseModel):
    term: TermRef | None
    is_demo: bool
    items: list[MyAttendanceItem]


class MySession(BaseModel):
    held_on: date
    slot: int
    status: str


class MySectionAttendance(AttendanceSummary):
    section: SectionRef
    subject: SubjectRef
    term: TermRef
    is_demo: bool
    sessions: list[MySession]
