# ruff: noqa: F811  (fixtures imported from test_attendance are redefined as parameters)
"""Assessments and results (ACADEMIC-008, 009; US-07): creating, entering scores, publishing,
revising, the student's own results, and the access matrix (PRD §11, ACADEMIC-010).

Reuses the attendance world: CS301 A taught by `faculty`, with `student` and `mech_student`
enrolled; ME201 A (MECH) taught by nobody. The clock starts at 2026-10-21 12:00 UTC.
"""

from typing import Any

import pytest
from sqlalchemy import Connection

from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World
from tests.integration.conftest import Clock
from tests.integration.test_attendance import cs, not_found, ok, world  # noqa: F401

pytestmark = pytest.mark.integration

SECTIONS = f"{CAMPUS}/sections"
ASSESSMENTS = f"{CAMPUS}/assessments"
QUIZ = {"name": "Quiz 1", "kind": "QUIZ", "max_score": "20", "held_on": "2026-10-20"}


def create(world: World, cs: dict[str, Any], who: str = "faculty", **body: Any) -> Any:
    return world.browser(who).post(f"{SECTIONS}/{cs['section']['id']}/assessments", QUIZ | body)


def created(world: World, cs: dict[str, Any], **body: Any) -> dict[str, Any]:
    return ok(create(world, cs, **body), 201)


def scores(cs: dict[str, Any], student: Any = "18.5", mech: Any = "12") -> list[dict[str, Any]]:
    def entry(enrollment: str, value: Any) -> dict[str, Any]:
        if value == "ABSENT":
            return {"enrollment_id": enrollment, "score": None, "absent": True}
        return {"enrollment_id": enrollment, "score": value, "absent": False}

    return [entry(cs["student"], student), entry(cs["mech_student"], mech)]


def enter(world: World, assessment: dict[str, Any], who: str = "faculty", **body: Any) -> Any:
    payload = {"version": assessment["version"]} | body
    return world.browser(who).send("PUT", f"{ASSESSMENTS}/{assessment['id']}/results", payload)


def entered(world: World, assessment: dict[str, Any], **body: Any) -> dict[str, Any]:
    return ok(enter(world, assessment, **body))


def publish(world: World, assessment: dict[str, Any], who: str = "faculty") -> Any:
    return world.browser(who).post(
        f"{ASSESSMENTS}/{assessment['id']}/publish", {"version": assessment["version"]}
    )


def scored_and_published(world: World, cs: dict[str, Any], **body: Any) -> dict[str, Any]:
    assessment = created(world, cs, **body)
    grid = entered(world, assessment, results=scores(cs))
    return ok(publish(world, grid["assessment"]))


def my_results(world: World, who: str = "student") -> dict[str, Any]:
    return ok(world.browser(who).get(f"{CAMPUS}/me/results"))


def my_assessments(world: World, who: str = "student") -> list[dict[str, Any]]:
    return [a for s in my_results(world, who)["items"] for a in s["assessments"]]


# --- creating (ACADEMIC-008) ---------------------------------------------------------------


def test_assigned_faculty_create_an_assessment(world: World, cs: dict[str, Any]) -> None:
    body = created(world, cs)
    assert (body["name"], body["kind"], body["max_score"], body["held_on"]) == (
        "Quiz 1",
        "QUIZ",
        20.0,
        "2026-10-20",
    )
    assert body["published_at"] is None and body["published_by"] is None
    assert body["counts"] == {"enrolled": 2, "entered": 0, "absent": 0}
    assert body["actions"] == {"enter_scores": True, "publish": True}
    listed = ok(world.browser("faculty").get(f"{SECTIONS}/{cs['section']['id']}/assessments"))
    assert [a["id"] for a in listed["items"]] == [body["id"]]


def test_assessment_fields_are_checked(world: World, cs: dict[str, Any]) -> None:
    for bad in (
        {"max_score": "0"},
        {"max_score": "-5"},
        {"max_score": "10000"},
        {"max_score": "10.555"},
        {"kind": "VIVA"},
        {"name": ""},
        {"name": "x" * 81},
        {"held_on": "2026-06-30"},  # before the term
        {"held_on": "2026-12-16"},  # after it
        {"college_id": "anything"},
    ):
        response = create(world, cs, **bad)
        assert response.status_code == 422, bad


def test_who_may_create(world: World, cs: dict[str, Any]) -> None:
    assert not_found(create(world, cs, "other_faculty"))
    for who in ("dept_admin", "admin"):
        assert create(world, cs, who).status_code == 403, who
    for who in ("student", "mech_student"):
        response = create(world, cs, who)
        assert response.status_code == 403, who
    mech = world.browser("dept_admin").post(f"{SECTIONS}/{cs['mech']['id']}/assessments", QUIZ)
    assert not_found(mech)


# --- entering scores (ACADEMIC-008) --------------------------------------------------------


def test_faculty_enter_scores_and_absences(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    grid = entered(world, assessment, results=scores(cs, mech="ABSENT"))
    assert grid["assessment"]["version"] == 2
    assert grid["assessment"]["counts"] == {"enrolled": 2, "entered": 2, "absent": 1}
    assert [(r["display_name"], r["score"], r["absent"], r["revised"]) for r in grid["rows"]] == [
        ("Mech Student", None, True, False),
        ("Student", 18.5, False, False),
    ]
    # Partial saves and clearing work before publishing.
    clear = [{"enrollment_id": cs["mech_student"], "score": None, "absent": False}]
    again = entered(world, grid["assessment"], results=clear)
    assert [(r["display_name"], r["score"], r["absent"]) for r in again["rows"]] == [
        ("Mech Student", None, False),
        ("Student", 18.5, False),
    ]
    assert again["assessment"]["counts"]["entered"] == 1


def test_score_above_max_is_rejected(world: World, cs: dict[str, Any]) -> None:
    """US-07: score > max → 422."""
    assessment = created(world, cs)
    too_high = enter(world, assessment, results=scores(cs, student="20.01"))
    assert too_high.status_code == 422
    assert [d["field"] for d in error_of(too_high)["details"]] == ["results.0.score"]
    for bad in ("-1", "1.005"):
        assert enter(world, assessment, results=scores(cs, student=bad)).status_code == 422
    both = [{"enrollment_id": cs["student"], "score": "5", "absent": True}]
    assert enter(world, assessment, results=both).status_code == 422
    ok(enter(world, assessment, results=scores(cs, student="20", mech="0")))


def test_scores_only_for_enrolled_students_once(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    twice = enter(world, assessment, results=scores(cs) + scores(cs)[:1])
    assert [d["field"] for d in error_of(twice)["details"]] == ["results.2.enrollment_id"]
    other = ok(world.browser("admin").get(f"{SECTIONS}/{cs['mech']['id']}/enrollments"))["items"]
    stranger = [{"enrollment_id": other[0]["id"], "score": "1", "absent": False}]
    assert [
        d["field"] for d in error_of(enter(world, assessment, results=stranger))["details"]
    ] == ["results.0.enrollment_id"]


def test_score_entry_checks_the_version(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    entered(world, assessment, results=scores(cs))
    stale = enter(world, assessment, results=scores(cs, student="1"))
    assert stale.status_code == 409
    assert error_of(stale)["code"] == "version_conflict"


def test_who_may_enter_scores(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    assert not_found(enter(world, assessment, "other_faculty", results=scores(cs)))
    for who in ("dept_admin", "admin", "student"):
        response = enter(world, assessment, who, results=scores(cs))
        assert response.status_code == 403, who


# --- reading the section's results (ACADEMIC-010) ------------------------------------------


def test_who_may_read_section_results(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    entered(world, assessment, results=scores(cs))
    for who in ("faculty", "dept_admin", "admin"):
        grid = ok(world.browser(who).get(f"{ASSESSMENTS}/{assessment['id']}/results"))
        assert len(grid["rows"]) == 2, who
        ok(world.browser(who).get(f"{SECTIONS}/{cs['section']['id']}/assessments"))
    reader = ok(world.browser("admin").get(f"{ASSESSMENTS}/{assessment['id']}/results"))
    assert reader["assessment"]["actions"] == {"enter_scores": False, "publish": False}
    dept = ok(world.browser("dept_admin").get(f"{ASSESSMENTS}/{assessment['id']}/results"))
    assert dept["assessment"]["actions"] == {"enter_scores": False, "publish": True}
    assert not_found(
        world.browser("other_faculty").get(f"{ASSESSMENTS}/{assessment['id']}/results")
    )
    for who in ("student", "mech_student"):
        response = world.browser(who).get(f"{ASSESSMENTS}/{assessment['id']}/results")
        assert response.status_code == 403, who
        assert "18.5" not in response.text and "Mech Student" not in response.text
        listed = world.browser(who).get(f"{SECTIONS}/{cs['section']['id']}/assessments")
        assert listed.status_code == 403 and "Quiz 1" not in listed.text


# --- publishing (ACADEMIC-009, US-07) ------------------------------------------------------


def test_unpublished_results_never_reach_students(world: World, cs: dict[str, Any]) -> None:
    """US-07: before publish, student GET results excludes the assessment."""
    assessment = created(world, cs)
    entered(world, assessment, results=scores(cs))
    mine = my_results(world)
    assert mine["term"]["id"] == cs["term"]["id"]
    assert my_assessments(world) == []
    assert "Quiz 1" not in str(mine)


def test_publishing_notifies_each_enrolled_student_once(
    world: World, cs: dict[str, Any], conn: Connection
) -> None:
    """US-07: enrolled students get one notification each; nobody else gets any."""
    published = scored_and_published(world, cs)
    assert published["published_at"] == "2026-10-21T12:00:00Z"
    assert published["published_by"]["display_name"] == "Faculty"
    assert published["actions"]["publish"] is False
    rows = conn.exec_driver_sql(
        "SELECT u.display_name, n.type, n.title, n.subject_type, n.subject_id::text "
        "FROM notifications n JOIN users u ON u.id = n.user_id ORDER BY u.display_name"
    ).all()
    assert [r[0] for r in rows] == ["Mech Student", "Student"]
    for _, kind, title, subject_type, subject_id in rows:
        assert kind == "ASSESSMENT_PUBLISHED"
        assert title == "Results published: CS301 Quiz 1"
        assert (subject_type, subject_id) == ("ASSESSMENT", published["id"])
    # No score in any notification (Rules R-2.11); the publish is audited.
    assert scalar(conn, "SELECT count(*) FROM notifications WHERE title LIKE '%18%'") == 0
    assert (
        scalar(
            conn, "SELECT count(*) FROM audit_log WHERE action = 'academic.assessment_published'"
        )
        == 1
    )


def test_published_results_show_for_their_student_only(world: World, cs: dict[str, Any]) -> None:
    scored_and_published(world, cs)
    [quiz] = my_assessments(world)
    assert (quiz["name"], quiz["max_score"], quiz["score"], quiz["absent"], quiz["revised"]) == (
        "Quiz 1",
        20.0,
        18.5,
        False,
        False,
    )
    mine = my_results(world)
    assert [s["subject"]["code"] for s in mine["items"]] == ["CS301"]
    assert "12" not in str([a["score"] for a in my_assessments(world)])
    [theirs] = my_assessments(world, "mech_student")
    assert theirs["score"] == 12.0
    for who in ("faculty", "admin"):
        assert world.browser(who).get(f"{CAMPUS}/me/results").status_code == 403


def test_publishing_needs_every_student_scored_and_happens_once(
    world: World, cs: dict[str, Any]
) -> None:
    assessment = created(world, cs)
    grid = entered(world, assessment, results=scores(cs)[:1])
    missing = publish(world, grid["assessment"])
    assert missing.status_code == 422
    assert "1 missing" in error_of(missing)["details"][0]["message"]
    grid = entered(world, grid["assessment"], results=scores(cs)[1:])
    published = ok(publish(world, grid["assessment"]))
    again = publish(world, published)
    assert again.status_code == 409
    assert error_of(again)["code"] == "already_published"


def test_who_may_publish(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    grid = entered(world, assessment, results=scores(cs))["assessment"]
    assert not_found(publish(world, grid, "other_faculty"))
    for who in ("admin", "student"):
        assert publish(world, grid, who).status_code == 403, who
    published = ok(publish(world, grid, "dept_admin"))  # a department admin of CSE may
    assert published["published_by"]["display_name"] == "Dept Admin"


# --- revising after publishing (ACADEMIC-009, US-07) ---------------------------------------


def test_revising_needs_a_reason_and_marks_the_result(
    world: World, cs: dict[str, Any], conn: Connection, clock: Clock
) -> None:
    """US-07: post-publish change without reason → 422; with reason → the result is "Revised"."""
    published = scored_and_published(world, cs)
    clock.advance(days=2)
    change = [{"enrollment_id": cs["student"], "score": "19.5", "absent": False}]
    missing = enter(world, published, results=change)
    assert missing.status_code == 422
    assert error_of(missing)["details"][0]["field"] == "reason"
    assert enter(world, published, results=change, reason="  ").status_code == 422
    clear = [{"enrollment_id": cs["student"], "score": None, "absent": False}]
    assert enter(world, published, results=clear, reason="x").status_code == 422

    grid = entered(world, published, results=change, reason="Re-marked question 4")
    by_name = {r["display_name"]: r for r in grid["rows"]}
    assert (by_name["Student"]["score"], by_name["Student"]["revised"]) == (19.5, True)
    assert by_name["Mech Student"]["revised"] is False
    [quiz] = my_assessments(world)
    assert (quiz["score"], quiz["revised"]) == (19.5, True)
    assert my_assessments(world, "mech_student")[0]["revised"] is False

    # The student is told (no score in the title); the audit names who changed, not values.
    told = (
        conn.exec_driver_sql(
            "SELECT n.title FROM notifications n JOIN users u ON u.id = n.user_id "
            "WHERE n.type = 'ASSESSMENT_REVISED'"
        )
        .scalars()
        .all()
    )
    assert told == ["Result revised: CS301 Quiz 1"]
    reason, changed, text = conn.exec_driver_sql(
        "SELECT reason, metadata->'enrollment_ids', metadata::text FROM audit_log "
        "WHERE action = 'academic.results_changed'"
    ).one()
    assert reason == "Re-marked question 4" and changed == [cs["student"]]
    assert "19.5" not in text and "18.5" not in text


def test_an_unchanged_save_after_publishing_changes_nothing(
    world: World, cs: dict[str, Any], conn: Connection
) -> None:
    published = scored_and_published(world, cs)
    same = entered(world, published, results=scores(cs)[:1])  # no reason needed: nothing changes
    assert same["assessment"]["version"] == published["version"]
    assert scalar(conn, "SELECT count(*) FROM notifications WHERE type = 'ASSESSMENT_REVISED'") == 0


def test_only_assigned_faculty_revise(world: World, cs: dict[str, Any]) -> None:
    published = scored_and_published(world, cs)
    change = [{"enrollment_id": cs["student"], "score": "1", "absent": False}]
    for who in ("dept_admin", "admin"):
        response = enter(world, published, who, results=change, reason="r")
        assert response.status_code == 403, who


# --- what results block --------------------------------------------------------------------


def test_an_enrollment_with_results_cannot_be_removed(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    entered(world, assessment, results=scores(cs))
    removed = world.browser("admin").send("DELETE", f"{CAMPUS}/enrollments/{cs['mech_student']}")
    assert removed.status_code == 409
    assert error_of(removed)["code"] == "enrollment_has_records"


def test_another_colleges_student_sees_nothing(world: World, cs: dict[str, Any]) -> None:
    scored_and_published(world, cs)
    theirs = my_results(world, "river_student")
    assert theirs["items"] == [] and "Quiz 1" not in str(theirs)


# --- correcting a draft (edit / delete before publishing) ----------------------------------


def edit(world: World, assessment: dict[str, Any], who: str = "faculty", **body: Any) -> Any:
    return world.browser(who).patch(
        f"{ASSESSMENTS}/{assessment['id']}", {"version": assessment["version"]} | body
    )


def test_faculty_correct_a_draft_assessment(
    world: World, cs: dict[str, Any], conn: Connection
) -> None:
    assessment = created(world, cs)
    changed = ok(
        edit(world, assessment, name="Quiz 1 (retest)", kind="OTHER", held_on="2026-10-19")
    )
    assert (changed["name"], changed["kind"], changed["held_on"]) == (
        "Quiz 1 (retest)",
        "OTHER",
        "2026-10-19",
    )
    assert changed["version"] == assessment["version"] + 1
    assert (
        scalar(conn, "SELECT count(*) FROM audit_log WHERE action = 'academic.assessment_updated'")
        == 1
    )
    stale = edit(world, assessment, name="Again")
    assert stale.status_code == 409 and error_of(stale)["code"] == "version_conflict"


def test_the_maximum_cannot_drop_below_an_entered_score(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    grid = entered(world, assessment, results=scores(cs, student="18.5", mech="12"))["assessment"]
    too_low = edit(world, grid, max_score="18")
    assert too_low.status_code == 422
    assert error_of(too_low)["details"][0]["field"] == "max_score"
    after = ok(edit(world, grid, max_score="18.5"))
    assert after["max_score"] == 18.5
    assert edit(world, after, held_on="2026-06-30").status_code == 422  # outside the term


def test_a_published_assessment_is_not_edited_or_deleted(world: World, cs: dict[str, Any]) -> None:
    published = scored_and_published(world, cs)
    refused = edit(world, published, name="Renamed")
    assert refused.status_code == 409 and error_of(refused)["code"] == "already_published"
    gone = world.browser("faculty").send("DELETE", f"{ASSESSMENTS}/{published['id']}")
    assert gone.status_code == 409 and error_of(gone)["code"] == "already_published"


def test_faculty_delete_a_draft_with_its_scores(
    world: World, cs: dict[str, Any], conn: Connection
) -> None:
    assessment = created(world, cs)
    entered(world, assessment, results=scores(cs))
    deleted = world.browser("faculty").send("DELETE", f"{ASSESSMENTS}/{assessment['id']}")
    assert deleted.status_code == 204
    listed = ok(world.browser("faculty").get(f"{SECTIONS}/{cs['section']['id']}/assessments"))
    assert listed["items"] == []
    assert scalar(conn, "SELECT count(*) FROM assessment_results") == 0
    assert (
        scalar(conn, "SELECT count(*) FROM audit_log WHERE action = 'academic.assessment_deleted'")
        == 1
    )
    # Its students could now leave the section (nothing of theirs remains).
    removed = world.browser("admin").send("DELETE", f"{CAMPUS}/enrollments/{cs['mech_student']}")
    assert removed.status_code == 204


def test_who_may_correct_a_draft(world: World, cs: dict[str, Any]) -> None:
    assessment = created(world, cs)
    assert not_found(edit(world, assessment, "other_faculty", name="X"))
    assert not_found(
        world.browser("other_faculty").send("DELETE", f"{ASSESSMENTS}/{assessment['id']}")
    )
    for who in ("dept_admin", "admin", "student"):
        assert edit(world, assessment, who, name="X").status_code == 403, who
        response = world.browser(who).send("DELETE", f"{ASSESSMENTS}/{assessment['id']}")
        assert response.status_code == 403, who
    assert edit(world, assessment, name="X", college_id="anything").status_code == 422
