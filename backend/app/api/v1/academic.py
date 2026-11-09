"""Academic Hub routes (architecture.md §11.1, ACADEMIC-001…009). The college comes from
`Campus`; app/services/academic_setup.py loads objects inside it and applies
app/policies/academic.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import Campus, Db, Now, no_store
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.schemas.academic import (
    AssessmentActions,
    AssessmentCounts,
    AssessmentCreate,
    AssessmentOut,
    AssessmentPage,
    AssessmentPublish,
    AssessmentResults,
    AttendanceCounts,
    AttendanceRecordOut,
    AttendanceSessionCreate,
    AttendanceSessionDetail,
    AttendanceSessionEdit,
    AttendanceSessionOut,
    AttendanceSessionPage,
    EnrollmentAdd,
    EnrollmentImport,
    EnrollmentOut,
    EnrollmentPage,
    EnrollmentsAdded,
    InstructorsSet,
    MyAttendance,
    MyAttendanceItem,
    MyClass,
    MyResult,
    MyResults,
    MySectionAttendance,
    MySession,
    MySubjectResults,
    MyTimetable,
    Person,
    ResultRow,
    ResultsSave,
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
from app.services import attendance, results
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


# --- attendance (ACADEMIC-005…007) ---------------------------------------------------------


def _session_out(view: attendance.SessionView) -> AttendanceSessionOut:
    s = view.session
    return AttendanceSessionOut(
        id=s.id,
        section_id=s.section_id,
        held_on=s.held_on,
        slot=s.slot,
        version=s.version,
        recorded_by=Person(membership_id=view.recorded_by[0], display_name=view.recorded_by[1]),
        counts=AttendanceCounts(
            present=view.counts["PRESENT"],
            absent=view.counts["ABSENT"],
            excused=view.counts["EXCUSED"],
        ),
        edit=view.edit.value if view.edit else None,
        edit_window_closes_at=view.edit_window_closes_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _session_detail(
    view: attendance.SessionView, records: list[attendance.RecordRow]
) -> AttendanceSessionDetail:
    return AttendanceSessionDetail(
        **_session_out(view).model_dump(),
        records=[
            AttendanceRecordOut(
                enrollment_id=r.record.enrollment_id,
                membership_id=r.membership_id,
                display_name=r.display_name,
                status=r.record.status,
            )
            for r in records
        ],
    )


@router.post("/sections/{section_id}/attendance-sessions", status_code=201)
def record_attendance(
    section_id: uuid.UUID, body: AttendanceSessionCreate, campus: Campus, db: Db, now: Now
) -> AttendanceSessionDetail:
    view, records = attendance.record_session(
        db,
        campus,
        section_id,
        held_on=body.held_on,
        slot=body.slot,
        marks=[(m.enrollment_id, m.status) for m in body.records],
        now=now,
    )
    return _session_detail(view, records)


@router.get("/sections/{section_id}/attendance-sessions")
def list_attendance_sessions(
    section_id: uuid.UUID,
    campus: Campus,
    db: Db,
    now: Now,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> AttendanceSessionPage:
    views, next_cursor = attendance.list_sessions(
        db, campus, section_id, cursor=decode_cursor(cursor), limit=limit, now=now
    )
    return AttendanceSessionPage(items=[_session_out(v) for v in views], next_cursor=next_cursor)


@router.get("/attendance-sessions/{session_id}")
def get_attendance_session(
    session_id: uuid.UUID, campus: Campus, db: Db, now: Now
) -> AttendanceSessionDetail:
    return _session_detail(*attendance.get_session(db, campus, session_id, now))


@router.patch("/attendance-sessions/{session_id}")
def edit_attendance_session(
    session_id: uuid.UUID, body: AttendanceSessionEdit, campus: Campus, db: Db, now: Now
) -> AttendanceSessionDetail:
    view, records = attendance.edit_session(
        db,
        campus,
        session_id,
        version=body.version,
        marks=[(m.enrollment_id, m.status) for m in body.records],
        reason=body.reason,
        now=now,
    )
    return _session_detail(view, records)


@router.get("/me/attendance")
def my_attendance(campus: Campus, db: Db) -> MyAttendance:
    term, rows = attendance.my_attendance(db, campus)
    return MyAttendance(
        term=TermRef.from_term(term) if term else None,
        is_demo=campus.college.is_demo,
        items=[
            MyAttendanceItem(
                section=SectionRef(id=r.section.id, name=r.section.name),
                subject=SubjectRef.from_subject(r.subject),
                held=r.summary.held,
                attended=r.summary.attended,
                excused=r.summary.excused,
                percentage=r.summary.percentage,
            )
            for r in rows
        ],
    )


@router.get("/me/attendance/{section_id}")
def my_section_attendance(section_id: uuid.UUID, campus: Campus, db: Db) -> MySectionAttendance:
    detail = attendance.my_section_attendance(db, campus, section_id)
    return MySectionAttendance(
        section=SectionRef(id=detail.section.id, name=detail.section.name),
        subject=SubjectRef.from_subject(detail.subject),
        term=TermRef.from_term(detail.term),
        is_demo=campus.college.is_demo,
        held=detail.summary.held,
        attended=detail.summary.attended,
        excused=detail.summary.excused,
        percentage=detail.summary.percentage,
        sessions=[MySession(held_on=d, slot=s, status=st) for d, s, st in detail.sessions],
    )


# --- assessments and results (ACADEMIC-008, 009) -------------------------------------------


def _number(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _assessment_out(view: results.AssessmentView) -> AssessmentOut:
    a = view.assessment
    return AssessmentOut(
        id=a.id,
        section_id=a.section_id,
        name=a.name,
        kind=a.kind,
        max_score=float(a.max_score),
        held_on=a.held_on,
        version=a.version,
        published_at=a.published_at,
        published_by=(
            Person(membership_id=view.published_by[0], display_name=view.published_by[1])
            if view.published_by
            else None
        ),
        counts=AssessmentCounts(
            enrolled=view.counts.enrolled,
            entered=view.counts.entered,
            absent=view.counts.absent,
        ),
        actions=AssessmentActions(enter_scores=view.may_enter_scores, publish=view.may_publish),
        created_at=a.created_at,
    )


def _results_out(
    view: results.AssessmentView, rows: list[results.ResultRowView]
) -> AssessmentResults:
    return AssessmentResults(
        assessment=_assessment_out(view),
        rows=[
            ResultRow(
                enrollment_id=r.enrollment_id,
                membership_id=r.membership_id,
                display_name=r.display_name,
                score=_number(r.result.score) if r.result else None,
                absent=bool(r.result and r.result.is_absent),
                revised=bool(r.result and r.result.revised_at),
            )
            for r in rows
        ],
    )


@router.post("/sections/{section_id}/assessments", status_code=201)
def create_assessment(
    section_id: uuid.UUID, body: AssessmentCreate, campus: Campus, db: Db, now: Now
) -> AssessmentOut:
    view = results.create_assessment(
        db,
        campus,
        section_id,
        name=body.name,
        kind=body.kind,
        max_score=body.max_score,
        held_on=body.held_on,
        now=now,
    )
    return _assessment_out(view)


@router.get("/sections/{section_id}/assessments")
def list_assessments(
    section_id: uuid.UUID,
    campus: Campus,
    db: Db,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> AssessmentPage:
    views, next_cursor = results.list_assessments(
        db, campus, section_id, cursor=decode_cursor(cursor), limit=limit
    )
    return AssessmentPage(items=[_assessment_out(v) for v in views], next_cursor=next_cursor)


@router.get("/assessments/{assessment_id}/results")
def get_assessment_results(assessment_id: uuid.UUID, campus: Campus, db: Db) -> AssessmentResults:
    return _results_out(*results.get_results(db, campus, assessment_id))


@router.put("/assessments/{assessment_id}/results")
def save_assessment_results(
    assessment_id: uuid.UUID, body: ResultsSave, campus: Campus, db: Db, now: Now
) -> AssessmentResults:
    view, rows = results.save_results(
        db,
        campus,
        assessment_id,
        version=body.version,
        entries=[results.ScoreInput(e.enrollment_id, e.score, e.absent) for e in body.results],
        reason=body.reason,
        now=now,
    )
    return _results_out(view, rows)


@router.post("/assessments/{assessment_id}/publish")
def publish_assessment(
    assessment_id: uuid.UUID, body: AssessmentPublish, campus: Campus, db: Db, now: Now
) -> AssessmentOut:
    view = results.publish_assessment(db, campus, assessment_id, version=body.version, now=now)
    return _assessment_out(view)


@router.get("/me/results")
def my_results(campus: Campus, db: Db) -> MyResults:
    term, groups = results.my_results(db, campus)
    return MyResults(
        term=TermRef.from_term(term) if term else None,
        is_demo=campus.college.is_demo,
        items=[
            MySubjectResults(
                section=SectionRef(id=g.section.id, name=g.section.name),
                subject=SubjectRef.from_subject(g.subject),
                assessments=[
                    MyResult(
                        id=r.assessment.id,
                        name=r.assessment.name,
                        kind=r.assessment.kind,
                        max_score=float(r.assessment.max_score),
                        held_on=r.assessment.held_on,
                        published_at=r.assessment.published_at,  # type: ignore[arg-type]
                        score=_number(r.result.score) if r.result else None,
                        absent=bool(r.result and r.result.is_absent),
                        revised=bool(r.result and r.result.revised_at),
                    )
                    for r in g.results
                ],
            )
            for g in groups
        ],
    )
