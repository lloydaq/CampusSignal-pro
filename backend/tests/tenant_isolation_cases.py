"""Registry for the tenant-isolation suite (TENANT-005, PRD §17).

Every /api/v1/campus operation is listed here; `test_route_inventory` fails when one is
missing, so a new route can't skip the suite. The suite (tests/integration/
test_tenant_isolation.py) builds the two-college world, signs in as Northfield's college
admin (the widest campus permissions) and, per kind:

- OBJECT: calls the route on a Riverside object. Expect the same 404 as for an object that
  doesn't exist (TENANT-002) and no Riverside data in the body.
- LIST: calls the route while Riverside has matching data. Expect 200 and no Riverside data.
- CREATE: sends a body that names Riverside's college. Expect 422 (unknown field): the acting
  college only ever comes from the session (TENANT-001).

A case may name another Northfield member (`who`) for a route the college admin's role
doesn't use, such as a student's own timetable.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CAMPUS = "/api/v1/campus"
ROSTER_HEADER = "roll_number,full_name,department_code,program,admission_year,email"


class Kind(StrEnum):
    OBJECT = "object"
    LIST = "list"
    CREATE = "create"


@dataclass(frozen=True)
class IsolationCase:
    kind: Kind
    # Given the world (tests/integration/campus_world.World), the concrete path and JSON body.
    request: Callable[[Any], tuple[str, dict[str, Any] | None]]
    who: str = "admin"


def _static(
    path: str, body: dict[str, Any] | None = None
) -> Callable[[Any], tuple[str, dict[str, Any] | None]]:
    return lambda world: (path, body)


CASES: dict[tuple[str, str], IsolationCase] = {
    # departments
    ("GET", f"{CAMPUS}/departments"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/departments?include_archived=true")
    ),
    ("POST", f"{CAMPUS}/departments"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/departments",
            {"code": "X1", "name": "X", "college_id": str(w.river.id)},
        ),
    ),
    ("GET", f"{CAMPUS}/departments/{{department_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/departments/{w.river.departments['CSE'].id}", None)
    ),
    ("PATCH", f"{CAMPUS}/departments/{{department_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/departments/{w.river.departments['CSE'].id}", {"name": "Hacked"}),
    ),
    # roster
    ("GET", f"{CAMPUS}/roster"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/roster?query=R-001")),
    ("POST", f"{CAMPUS}/roster/import"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/roster/import",
            {
                "csv": ROSTER_HEADER + "\nX,X,CSE,B,2025,",
                "college_id": str(w.river.id),
            },
        ),
    ),
    # invites
    ("GET", f"{CAMPUS}/invites"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/invites")),
    ("POST", f"{CAMPUS}/invites"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/invites",
            {"email": "x@riverside.example", "kind": "STAFF", "college_id": str(w.river.id)},
        ),
    ),
    # members and grants
    ("GET", f"{CAMPUS}/members"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/members?query=River")
    ),
    ("PATCH", f"{CAMPUS}/members/{{membership_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_student'].id}",
            {"status": "ENDED", "reason": "x"},
        ),
    ),
    ("POST", f"{CAMPUS}/members/{{membership_id}}/grants"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_admin'].id}/grants",
            {"role": "ISSUE_COORDINATOR"},
        ),
    ),
    ("DELETE", f"{CAMPUS}/members/{{membership_id}}/grants/{{grant_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/members/{w.members['river_admin'].id}/grants/{w.river_admin_grant.id}",
            None,
        ),
    ),
    # membership requests (approval queue)
    ("GET", f"{CAMPUS}/membership-requests"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/membership-requests")
    ),
    ("POST", f"{CAMPUS}/membership-requests/{{request_id}}/approve"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/membership-requests/{w.river_request.id}/approve", None),
    ),
    ("POST", f"{CAMPUS}/membership-requests/{{request_id}}/reject"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/membership-requests/{w.river_request.id}/reject", {"reason": "x"}),
    ),
    # notices
    ("GET", f"{CAMPUS}/notices"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/notices")),
    ("POST", f"{CAMPUS}/notices"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/notices",
            {
                "title": "X",
                "body": "X",
                "category": "GENERAL",
                "scope": "COLLEGE",
                "college_id": str(w.river.id),
            },
        ),
    ),
    ("GET", f"{CAMPUS}/notices/{{notice_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/notices/{w.river_notice['id']}", None)
    ),
    ("PATCH", f"{CAMPUS}/notices/{{notice_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/notices/{w.river_notice['id']}",
            {"version": w.river_notice["version"], "title": "Hacked"},
        ),
    ),
    ("POST", f"{CAMPUS}/notices/{{notice_id}}/publish"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/notices/{w.river_draft['id']}/publish",
            {"version": w.river_draft["version"]},
        ),
    ),
    ("POST", f"{CAMPUS}/notices/{{notice_id}}/withdraw"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/notices/{w.river_notice['id']}/withdraw", {"reason": "x"}),
    ),
    # issues (the queue lists the whole college: the widest issue list there is)
    ("GET", f"{CAMPUS}/issues"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/issues?scope=queue")),
    ("POST", f"{CAMPUS}/issues"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/issues",
            {
                "category": "OTHER",
                "title": "X",
                "description": "X",
                "location": "X",
                "college_id": str(w.river.id),
            },
        ),
    ),
    ("GET", f"{CAMPUS}/issues/{{issue_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/issues/{w.river_issue['id']}", None)
    ),
    ("POST", f"{CAMPUS}/issues/{{issue_id}}/transitions"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/issues/{w.river_issue['id']}/transitions",
            {"to_status": "ACKNOWLEDGED", "version": w.river_issue["version"]},
        ),
    ),
    ("POST", f"{CAMPUS}/issues/{{issue_id}}/assignment"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/issues/{w.river_issue['id']}/assignment",
            {"assignee_id": str(w.members["admin"].id), "version": w.river_issue["version"]},
        ),
    ),
    ("POST", f"{CAMPUS}/issues/{{issue_id}}/updates"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/issues/{w.river_issue['id']}/updates", {"body": "Hello"}),
    ),
    # the assignee picker: Riverside's college admin is faculty, so a name search would find them
    ("GET", f"{CAMPUS}/assignees"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/assignees?query=River")
    ),
    # community (the college feed and a department feed both list; posts and comments are objects)
    ("GET", f"{CAMPUS}/posts"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/posts")),
    ("POST", f"{CAMPUS}/posts"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/posts",
            {"body": "X", "visibility": "COLLEGE", "college_id": str(w.river.id)},
        ),
    ),
    ("GET", f"{CAMPUS}/posts/{{post_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}", None)
    ),
    ("PATCH", f"{CAMPUS}/posts/{{post_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}", {"body": "Hacked"})
    ),
    ("DELETE", f"{CAMPUS}/posts/{{post_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}", None)
    ),
    ("GET", f"{CAMPUS}/posts/{{post_id}}/comments"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}/comments", None)
    ),
    ("POST", f"{CAMPUS}/posts/{{post_id}}/comments"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}/comments", {"body": "X"})
    ),
    ("PATCH", f"{CAMPUS}/comments/{{comment_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/comments/{w.river_comment['id']}", {"body": "Hacked"})
    ),
    ("DELETE", f"{CAMPUS}/comments/{{comment_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/comments/{w.river_comment['id']}", None)
    ),
    ("PUT", f"{CAMPUS}/posts/{{post_id}}/reaction"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}/reaction", None)
    ),
    ("DELETE", f"{CAMPUS}/posts/{{post_id}}/reaction"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/posts/{w.river_post['id']}/reaction", None)
    ),
    # reports and moderation (the queue lists the whole college for a college admin)
    ("POST", f"{CAMPUS}/reports"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/reports", {"post_id": w.river_post["id"], "reason": "SPAM"}),
    ),
    ("GET", f"{CAMPUS}/moderation/reports"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/moderation/reports")
    ),
    ("POST", f"{CAMPUS}/moderation/reports/{{report_id}}/resolve"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/moderation/reports/{w.river_report['id']}/resolve",
            {"action": "HIDE", "reason": "x"},
        ),
    ),
    # academic setup (Riverside has a current term, a subject, a section with an instructor,
    # an enrolled student and a timetable entry: see test_tenant_isolation.world)
    ("GET", f"{CAMPUS}/terms"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/terms")),
    ("POST", f"{CAMPUS}/terms"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/terms",
            {
                "name": "X",
                "starts_on": "2027-01-01",
                "ends_on": "2027-05-01",
                "college_id": str(w.river.id),
            },
        ),
    ),
    ("PATCH", f"{CAMPUS}/terms/{{term_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/terms/{w.river_term['id']}", {"name": "Hacked"})
    ),
    ("GET", f"{CAMPUS}/subjects"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/subjects?query=RIV")
    ),
    ("POST", f"{CAMPUS}/subjects"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/subjects",
            {
                "department_id": str(w.north.departments["CSE"].id),
                "code": "X1",
                "name": "X",
                "college_id": str(w.river.id),
            },
        ),
    ),
    ("PATCH", f"{CAMPUS}/subjects/{{subject_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/subjects/{w.river_subject['id']}", {"name": "Hacked"})
    ),
    ("DELETE", f"{CAMPUS}/subjects/{{subject_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/subjects/{w.river_subject['id']}", None)
    ),
    ("GET", f"{CAMPUS}/sections"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/sections")),
    ("POST", f"{CAMPUS}/sections"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/sections",
            {
                "term_id": w.river_term["id"],
                "subject_id": w.river_subject["id"],
                "name": "X",
                "college_id": str(w.river.id),
            },
        ),
    ),
    ("GET", f"{CAMPUS}/sections/{{section_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}", None)
    ),
    ("PATCH", f"{CAMPUS}/sections/{{section_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}", {"name": "Hacked"})
    ),
    ("DELETE", f"{CAMPUS}/sections/{{section_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}", None)
    ),
    ("PUT", f"{CAMPUS}/sections/{{section_id}}/instructors"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/instructors",
            {"membership_ids": [str(w.members["faculty"].id)]},
        ),
    ),
    ("GET", f"{CAMPUS}/sections/{{section_id}}/enrollments"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}/enrollments", None)
    ),
    ("POST", f"{CAMPUS}/sections/{{section_id}}/enrollments"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/enrollments",
            {"membership_ids": [str(w.members["student"].id)]},
        ),
    ),
    ("POST", f"{CAMPUS}/sections/{{section_id}}/enrollments/import"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/enrollments/import",
            {"csv": "roll_number\nN-001\n"},
        ),
    ),
    ("DELETE", f"{CAMPUS}/enrollments/{{enrollment_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/enrollments/{w.river_enrollment['id']}", None)
    ),
    ("GET", f"{CAMPUS}/sections/{{section_id}}/timetable"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}/timetable", None)
    ),
    ("POST", f"{CAMPUS}/sections/{{section_id}}/timetable"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/timetable",
            {"weekday": 2, "starts_at": "09:00", "ends_at": "10:00", "room": "X"},
        ),
    ),
    ("PATCH", f"{CAMPUS}/timetable-entries/{{entry_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/timetable-entries/{w.river_entry['id']}", {"room": "Hacked"}),
    ),
    ("DELETE", f"{CAMPUS}/timetable-entries/{{entry_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/timetable-entries/{w.river_entry['id']}", None)
    ),
    # A student's own week: called by Northfield's student while Riverside's student has classes.
    ("GET", f"{CAMPUS}/me/timetable"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/me/timetable"), who="student"
    ),
    # Northfield's college admin is faculty; Riverside's (also faculty) teaches its section.
    ("GET", f"{CAMPUS}/teaching/sections"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/teaching/sections")
    ),
    # attendance (Riverside has a session recorded by its college admin, who teaches the section)
    ("POST", f"{CAMPUS}/sections/{{section_id}}/attendance-sessions"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/attendance-sessions",
            {
                "held_on": "2026-10-21",
                "slot": 2,
                "records": [{"enrollment_id": w.river_enrollment["id"], "status": "ABSENT"}],
            },
        ),
    ),
    ("GET", f"{CAMPUS}/sections/{{section_id}}/attendance-sessions"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}/attendance-sessions", None),
    ),
    ("GET", f"{CAMPUS}/attendance-sessions/{{session_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/attendance-sessions/{w.river_session['id']}", None)
    ),
    ("PATCH", f"{CAMPUS}/attendance-sessions/{{session_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/attendance-sessions/{w.river_session['id']}",
            {
                "version": 1,
                "reason": "x",
                "records": [{"enrollment_id": w.river_enrollment["id"], "status": "ABSENT"}],
            },
        ),
    ),
    # A student's own attendance: Northfield's student, while Riverside's has a session.
    ("GET", f"{CAMPUS}/me/attendance"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/me/attendance"), who="student"
    ),
    ("GET", f"{CAMPUS}/me/attendance/{{section_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/me/attendance/{w.river_section['id']}", None),
        who="student",
    ),
    # assessments and results (Riverside has a published, scored assessment)
    ("POST", f"{CAMPUS}/sections/{{section_id}}/assessments"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/sections/{w.river_section['id']}/assessments",
            {"name": "Hacked", "kind": "QUIZ", "max_score": "10", "held_on": "2026-10-20"},
        ),
    ),
    ("GET", f"{CAMPUS}/sections/{{section_id}}/assessments"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/sections/{w.river_section['id']}/assessments", None)
    ),
    ("PATCH", f"{CAMPUS}/assessments/{{assessment_id}}"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/assessments/{w.river_assessment['id']}",
            {"version": 3, "name": "Hacked"},
        ),
    ),
    ("DELETE", f"{CAMPUS}/assessments/{{assessment_id}}"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/assessments/{w.river_assessment['id']}", None)
    ),
    ("GET", f"{CAMPUS}/assessments/{{assessment_id}}/results"): IsolationCase(
        Kind.OBJECT, lambda w: (f"{CAMPUS}/assessments/{w.river_assessment['id']}/results", None)
    ),
    ("PUT", f"{CAMPUS}/assessments/{{assessment_id}}/results"): IsolationCase(
        Kind.OBJECT,
        lambda w: (
            f"{CAMPUS}/assessments/{w.river_assessment['id']}/results",
            {
                "version": 3,
                "reason": "x",
                "results": [{"enrollment_id": w.river_enrollment["id"], "score": "0"}],
            },
        ),
    ),
    ("POST", f"{CAMPUS}/assessments/{{assessment_id}}/publish"): IsolationCase(
        Kind.OBJECT,
        lambda w: (f"{CAMPUS}/assessments/{w.river_assessment['id']}/publish", {"version": 3}),
    ),
    # A student's own results: Northfield's student, while Riverside's has a published one.
    ("GET", f"{CAMPUS}/me/results"): IsolationCase(
        Kind.LIST, _static(f"{CAMPUS}/me/results"), who="student"
    ),
    # The home (HOME-004): Northfield's admin, student and faculty while Riverside has an open
    # report, a timetable, attendance and published results.
    ("GET", f"{CAMPUS}/home"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/home")),
    # college settings (the college is the session's; naming another one is refused)
    ("GET", f"{CAMPUS}/settings"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/settings")),
    ("PATCH", f"{CAMPUS}/settings"): IsolationCase(
        Kind.CREATE,
        lambda w: (
            f"{CAMPUS}/settings",
            {"attendance_edit_window_hours": 24, "college_id": str(w.river.id)},
        ),
    ),
    # audit
    ("GET", f"{CAMPUS}/audit-log"): IsolationCase(Kind.LIST, _static(f"{CAMPUS}/audit-log")),
}
