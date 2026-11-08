"""Academic setup routes (architecture.md §11.1, ACADEMIC-001…004). The college comes from
`Campus`; app/services/academic_setup.py loads objects inside it and applies
app/policies/academic.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.schemas.academic import (
    EnrollmentAdd,
    EnrollmentImport,
    EnrollmentOut,
    EnrollmentPage,
    EnrollmentsAdded,
    InstructorsSet,
    MyClass,
    MyTimetable,
    Person,
    SectionCreate,
    SectionOut,
    SectionPage,
    SectionRef,
    SectionUpdate,
    SubjectCreate,
    SubjectOut,
    SubjectPage,
    SubjectRef,
    SubjectUpdate,
    TeachingSections,
    TermCreate,
    TermList,
    TermOut,
    TermRef,
    TermUpdate,
    TimetableEntryCreate,
    TimetableEntryOut,
    TimetableEntryUpdate,
    TimetableList,
)
from app.schemas.campus import DepartmentRef
from app.services import academic_setup as service
from app.services.academic_setup import SectionView

router = APIRouter(prefix="/campus", tags=["academic"], dependencies=[Depends(no_store)])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]


def _section_out(view: SectionView) -> SectionOut:
    return SectionOut.build(
        view.section,
        view.term,
        view.subject,
        DepartmentRef.from_department(view.department),
        [Person(membership_id=m, display_name=n) for m, n in view.instructors],
        view.enrollment_count,
    )


# --- terms ---------------------------------------------------------------------------------


@router.get("/terms")
def list_terms(campus: Campus, db: Db) -> TermList:
    return TermList(items=[TermOut.from_term(t) for t in service.list_terms(db, campus)])


@router.post("/terms", status_code=201)
def create_term(body: TermCreate, campus: Campus, db: Db, now: Now) -> TermOut:
    term = service.create_term(
        db,
        campus,
        name=body.name,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        is_current=body.is_current,
        now=now,
    )
    return TermOut.from_term(term)


@router.patch("/terms/{term_id}")
def update_term(term_id: uuid.UUID, body: TermUpdate, campus: Campus, db: Db, now: Now) -> TermOut:
    term = service.update_term(
        db,
        campus,
        term_id,
        name=body.name,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        is_current=body.is_current,
        now=now,
    )
    return TermOut.from_term(term)


# --- subjects ------------------------------------------------------------------------------


@router.get("/subjects")
def list_subjects(
    campus: Campus,
    db: Db,
    department_id: uuid.UUID | None = None,
    query: Search = None,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> SubjectPage:
    rows, next_cursor = service.list_subjects(
        db,
        campus,
        department_id=department_id,
        query=query,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return SubjectPage(
        items=[
            SubjectOut(
                **SubjectRef.from_subject(s).model_dump(),
                department=DepartmentRef.from_department(d),
            )
            for s, d in rows
        ],
        next_cursor=next_cursor,
    )


@router.post("/subjects", status_code=201)
def create_subject(body: SubjectCreate, campus: Campus, db: Db, now: Now) -> SubjectOut:
    subject, department = service.create_subject(
        db, campus, department_id=body.department_id, code=body.code, name=body.name, now=now
    )
    return SubjectOut(
        **SubjectRef.from_subject(subject).model_dump(),
        department=DepartmentRef.from_department(department),
    )


@router.patch("/subjects/{subject_id}")
def update_subject(
    subject_id: uuid.UUID, body: SubjectUpdate, campus: Campus, db: Db, now: Now
) -> SubjectOut:
    subject, department = service.update_subject(db, campus, subject_id, name=body.name, now=now)
    return SubjectOut(
        **SubjectRef.from_subject(subject).model_dump(),
        department=DepartmentRef.from_department(department),
    )


@router.delete("/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: uuid.UUID, campus: Campus, db: Db) -> Response:
    service.delete_subject(db, campus, subject_id)
    return Response(status_code=204)


# --- sections and instructors --------------------------------------------------------------


@router.get("/sections")
def list_sections(
    campus: Campus,
    db: Db,
    term_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> SectionPage:
    views, next_cursor = service.list_sections(
        db,
        campus,
        term_id=term_id,
        subject_id=subject_id,
        department_id=department_id,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return SectionPage(items=[_section_out(v) for v in views], next_cursor=next_cursor)


@router.post("/sections", status_code=201)
def create_section(body: SectionCreate, campus: Campus, db: Db, now: Now) -> SectionOut:
    view = service.create_section(
        db, campus, term_id=body.term_id, subject_id=body.subject_id, name=body.name, now=now
    )
    return _section_out(view)


@router.get("/sections/{section_id}")
def get_section(section_id: uuid.UUID, campus: Campus, db: Db) -> SectionOut:
    return _section_out(service.get_section(db, campus, section_id))


@router.patch("/sections/{section_id}")
def update_section(
    section_id: uuid.UUID, body: SectionUpdate, campus: Campus, db: Db, now: Now
) -> SectionOut:
    return _section_out(service.update_section(db, campus, section_id, name=body.name, now=now))


@router.delete("/sections/{section_id}", status_code=204)
def delete_section(section_id: uuid.UUID, campus: Campus, db: Db) -> Response:
    service.delete_section(db, campus, section_id)
    return Response(status_code=204)


@router.put("/sections/{section_id}/instructors")
def set_instructors(
    section_id: uuid.UUID, body: InstructorsSet, campus: Campus, db: Db, now: Now
) -> SectionOut:
    return _section_out(service.set_instructors(db, campus, section_id, body.membership_ids, now))


# --- enrollments ---------------------------------------------------------------------------


@router.get("/sections/{section_id}/enrollments")
def list_enrollments(
    section_id: uuid.UUID,
    campus: Campus,
    db: Db,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> EnrollmentPage:
    rows, next_cursor = service.list_enrollments(
        db, campus, section_id, cursor=decode_cursor(cursor), limit=limit
    )
    return EnrollmentPage(
        items=[
            EnrollmentOut(
                id=r.enrollment.id,
                membership_id=r.enrollment.membership_id,
                display_name=r.display_name,
                roll_number=r.roll_number,
                department=DepartmentRef.from_department(r.department) if r.department else None,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


@router.post("/sections/{section_id}/enrollments", status_code=201)
def add_enrollments(
    section_id: uuid.UUID, body: EnrollmentAdd, campus: Campus, db: Db, now: Now
) -> EnrollmentsAdded:
    enrolled, already = service.add_enrollments(db, campus, section_id, body.membership_ids, now)
    return EnrollmentsAdded(enrolled=enrolled, already_enrolled=already)


@router.post("/sections/{section_id}/enrollments/import", status_code=201)
def import_enrollments(
    section_id: uuid.UUID, body: EnrollmentImport, campus: Campus, db: Db, now: Now
) -> EnrollmentsAdded:
    enrolled, already = service.import_enrollments(db, campus, section_id, text=body.csv, now=now)
    return EnrollmentsAdded(enrolled=enrolled, already_enrolled=already)


@router.delete("/enrollments/{enrollment_id}", status_code=204)
def remove_enrollment(enrollment_id: uuid.UUID, campus: Campus, db: Db) -> Response:
    service.remove_enrollment(db, campus, enrollment_id)
    return Response(status_code=204)


# --- timetable -----------------------------------------------------------------------------


@router.get("/sections/{section_id}/timetable")
def list_timetable(section_id: uuid.UUID, campus: Campus, db: Db) -> TimetableList:
    entries = service.list_timetable(db, campus, section_id)
    return TimetableList(items=[TimetableEntryOut.from_entry(e) for e in entries])


@router.post("/sections/{section_id}/timetable", status_code=201)
def add_timetable_entry(
    section_id: uuid.UUID, body: TimetableEntryCreate, campus: Campus, db: Db, now: Now
) -> TimetableEntryOut:
    entry = service.add_timetable_entry(
        db,
        campus,
        section_id,
        weekday=body.weekday,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        room=body.room,
        now=now,
    )
    return TimetableEntryOut.from_entry(entry)


@router.patch("/timetable-entries/{entry_id}")
def update_timetable_entry(
    entry_id: uuid.UUID, body: TimetableEntryUpdate, campus: Campus, db: Db, now: Now
) -> TimetableEntryOut:
    entry = service.update_timetable_entry(
        db,
        campus,
        entry_id,
        weekday=body.weekday,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        room=body.room,
        now=now,
    )
    return TimetableEntryOut.from_entry(entry)


@router.delete("/timetable-entries/{entry_id}", status_code=204)
def delete_timetable_entry(entry_id: uuid.UUID, campus: Campus, db: Db) -> Response:
    service.delete_timetable_entry(db, campus, entry_id)
    return Response(status_code=204)


# --- the student's week and the faculty member's sections ----------------------------------


@router.get("/me/timetable")
def my_timetable(campus: Campus, db: Db) -> MyTimetable:
    term, rows = service.my_timetable(db, campus)
    return MyTimetable(
        term=TermRef.from_term(term) if term else None,
        is_demo=campus.college.is_demo,
        classes=[
            MyClass(
                weekday=r.entry.weekday,
                starts_at=r.entry.starts_at,
                ends_at=r.entry.ends_at,
                room=r.entry.room,
                section=SectionRef(id=r.section.id, name=r.section.name),
                subject=SubjectRef.from_subject(r.subject),
            )
            for r in rows
        ],
    )


@router.get("/teaching/sections")
def teaching_sections(campus: Campus, db: Db) -> TeachingSections:
    term, views = service.teaching_sections(db, campus)
    return TeachingSections(
        term=TermRef.from_term(term) if term else None, items=[_section_out(v) for v in views]
    )
