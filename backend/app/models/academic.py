"""Academic Hub tables (ACADEMIC-001…007): terms, subjects, class sections, instructors,
enrollments, timetable entries and attendance. College-scoped like every campus table (see
app/models/college.py): references between them are composite (college_id, x_id) foreign keys."""

import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AcademicTerm(Base):
    """A term such as "2026-27 Odd semester". At most one is current per college."""

    __tablename__ = "academic_terms"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("college_id", "name"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name_length"),
        CheckConstraint("starts_on < ends_on", name="dates_in_order"),
        Index(
            "uq_academic_terms_one_current",
            "college_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    name: Mapped[str] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subject(Base):
    """A subject offered by a department. The code is unique within the college."""

    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("college_id", "code"),
        ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_subjects_department",
        ),
        CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'", name="code_format"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        Index("ix_subjects_college_id_department_id", "college_id", "department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClassSection(Base):
    """One subject taught in one term to one group ("CS301, section A"). Its department is the
    subject's department."""

    __tablename__ = "class_sections"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("term_id", "subject_id", "name"),
        ForeignKeyConstraint(
            ["college_id", "term_id"],
            ["academic_terms.college_id", "academic_terms.id"],
            name="fk_class_sections_term",
        ),
        ForeignKeyConstraint(
            ["college_id", "subject_id"],
            ["subjects.college_id", "subjects.id"],
            name="fk_class_sections_subject",
        ),
        CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
        Index("ix_class_sections_subject_id", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    term_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SectionInstructor(Base):
    """A faculty member assigned to teach a section. Deleted with the section."""

    __tablename__ = "section_instructors"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("section_id", "membership_id"),
        ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_section_instructors_section",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_section_instructors_membership",
        ),
        Index("ix_section_instructors_membership_id", "membership_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    """A student enrolled in a section. Attendance and results (Phase 7b/7c) point here, so a
    section with enrollments can't be deleted and an enrollment with records can't either."""

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("section_id", "membership_id"),
        ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_enrollments_section",
        ),
        ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_enrollments_membership",
        ),
        Index("ix_enrollments_membership_id", "membership_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimetableEntry(Base):
    """A weekly class slot. Entries of one section never overlap on the same weekday (an
    exclusion constraint; needs btree_gist for the equality parts). Weekday: 1 Monday … 7
    Sunday (ISO). Times are wall-clock times in the college's timezone."""

    __tablename__ = "timetable_entries"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_timetable_entries_section",
            ondelete="CASCADE",
        ),
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday"),
        CheckConstraint("starts_at < ends_at", name="times_in_order"),
        CheckConstraint("char_length(room) BETWEEN 1 AND 60", name="room_length"),
        ExcludeConstraint(
            ("section_id", "="),
            ("weekday", "="),
            (text("tsrange(DATE '2000-01-01' + starts_at, DATE '2000-01-01' + ends_at)"), "&&"),
            name="ex_timetable_entries_no_overlap",
            using="gist",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    weekday: Mapped[int] = mapped_column(SmallInteger)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    room: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AttendanceStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    EXCUSED = "EXCUSED"


class AttendanceSession(Base):
    """One class session of a section (ACADEMIC-005): a date and a period (slot 1-12). At
    most one per section, date and slot. `version` guards edits (ACADEMIC-006)."""

    __tablename__ = "attendance_sessions"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("section_id", "held_on", "slot"),
        ForeignKeyConstraint(
            ["college_id", "section_id"],
            ["class_sections.college_id", "class_sections.id"],
            name="fk_attendance_sessions_section",
        ),
        ForeignKeyConstraint(
            ["college_id", "recorded_by_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_attendance_sessions_recorded_by",
        ),
        CheckConstraint("slot BETWEEN 1 AND 12", name="slot"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    held_on: Mapped[date] = mapped_column(Date)
    slot: Mapped[int] = mapped_column(SmallInteger)
    recorded_by_membership_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AttendanceRecord(Base):
    """One enrolled student's status in one session. Its enrollment can't be removed while it
    exists (ACADEMIC-002: 409)."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("college_id", "id"),
        UniqueConstraint("session_id", "enrollment_id"),
        ForeignKeyConstraint(
            ["college_id", "session_id"],
            ["attendance_sessions.college_id", "attendance_sessions.id"],
            name="fk_attendance_records_session",
        ),
        ForeignKeyConstraint(
            ["college_id", "enrollment_id"],
            ["enrollments.college_id", "enrollments.id"],
            name="fk_attendance_records_enrollment",
        ),
        CheckConstraint("status IN ('PRESENT', 'ABSENT', 'EXCUSED')", name="status"),
        Index("ix_attendance_records_enrollment_id", "enrollment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("colleges.id"))
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(Text)
