"""Notices (NOTICE-001…006, DEPT-003/004; US-04, US-15): who publishes where, who reads what,
the draft → published → withdrawn lifecycle, ordering and the audit trail."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from app.models import MembershipKind, Role
from tests.integration.auth_helpers import error_of, scalar
from tests.integration.campus_world import CAMPUS, World, build_world
from tests.integration.conftest import Clock
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import add_member, make_user

pytestmark = pytest.mark.integration

NOTICES = f"{CAMPUS}/notices"
EVERYONE = ("admin", "dept_admin", "faculty", "student", "mech_student")
NO_SUCH_NOTICE = f"{NOTICES}/00000000-0000-4000-8000-000000000000"


@pytest.fixture
def world(session: Session, app_factory: Callable[..., FastAPI]) -> World:
    world = build_world(session, app_factory())
    # A MECH department admin, to tell "my department" from "another department".
    user = make_user(session, "mech_admin@northfield.example", name="Mech Admin")
    world.members["mech_admin"] = add_member(
        session,
        user,
        world.north,
        MembershipKind.FACULTY,
        department="MECH",
        roles=((Role.DEPARTMENT_ADMIN, "MECH"),),
    )
    session.commit()
    return world


def body(**changes: Any) -> dict[str, Any]:
    return {
        "title": "Exam timetable",
        "body": "Exams start **Monday**.",
        "category": "EXAMINATION",
        "scope": "COLLEGE",
        **changes,
    }


def create(who: Browser, **changes: Any) -> dict[str, Any]:
    response = who.post(NOTICES, body(**changes))
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def dept(world: World, code: str) -> str:
    return str(world.north.departments[code].id)


def ids(response: httpx2.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [n["id"] for n in response.json()["items"]]


def not_found(response: httpx2.Response) -> None:
    assert response.status_code == 404, response.text
    assert error_of(response)["code"] == "not_found"


# --- publishing and reading ---


def test_a_college_admin_publishes_a_college_notice_that_every_member_reads(world: World) -> None:
    published = create(world.browser("admin"), publish=True)

    assert published["status"] == "PUBLISHED"
    assert published["scope"] == "COLLEGE" and published["department"] is None
    assert published["published_at"] is not None and published["version"] == 2
    for who in EVERYONE:
        reader = world.browser(who)
        assert published["id"] in ids(reader.get(NOTICES)), who
        assert reader.get(f"{NOTICES}/{published['id']}").status_code == 200, who


def test_readers_never_see_who_wrote_a_notice_but_managers_do(world: World) -> None:
    published = create(world.browser("admin"), publish=True)
    seen_by_student = world.browser("student").get(f"{NOTICES}/{published['id']}").json()
    assert seen_by_student["author_name"] is None and seen_by_student["can_manage"] is False
    assert "Admin" not in str(seen_by_student)
    seen_by_admin = world.browser("admin").get(f"{NOTICES}/{published['id']}").json()
    assert seen_by_admin["author_name"] == "Admin" and seen_by_admin["can_manage"] is True


def test_a_department_notice_reaches_only_that_department(world: World) -> None:
    mech = create(
        world.browser("mech_admin"),
        scope="DEPARTMENT",
        department_id=dept(world, "MECH"),
        publish=True,
    )
    cse = create(
        world.browser("dept_admin"),
        scope="DEPARTMENT",
        department_id=dept(world, "CSE"),
        publish=True,
    )

    cse_reader, mech_reader = world.browser("student"), world.browser("mech_student")
    assert ids(cse_reader.get(NOTICES)) == [cse["id"]]
    assert ids(mech_reader.get(NOTICES)) == [mech["id"]]
    # Direct reads answer exactly like a notice that doesn't exist.
    refused = cse_reader.get(f"{NOTICES}/{mech['id']}")
    not_found(refused)
    assert error_of(refused)["message"] == error_of(cse_reader.get(NO_SUCH_NOTICE))["message"]
    assert "Exam timetable" not in refused.text
    # College admins read both; each department admin reads their own and not the other's.
    assert set(ids(world.browser("admin").get(NOTICES))) == {cse["id"], mech["id"]}
    assert ids(world.browser("dept_admin").get(NOTICES)) == [cse["id"]]
    # Faculty and staff follow their home department too.
    assert ids(world.browser("faculty").get(NOTICES)) == [cse["id"]]


def test_a_member_of_another_college_sees_nothing(world: World) -> None:
    published = create(world.browser("admin"), publish=True)
    outsider = world.browser("river_student")
    assert ids(outsider.get(NOTICES)) == []
    not_found(outsider.get(f"{NOTICES}/{published['id']}"))


def test_only_college_and_department_admins_can_create_notices(world: World) -> None:
    for who in ("student", "mech_student", "faculty"):
        response = world.browser(who).post(NOTICES, body())
        assert response.status_code == 403, who
        assert error_of(response)["code"] == "forbidden"
        assert "Exam timetable" not in response.text


def test_department_admins_publish_only_in_their_own_department(world: World) -> None:
    cse_admin = world.browser("dept_admin")
    # College-wide: refused. Another department: not theirs, so it doesn't exist for them.
    assert cse_admin.post(NOTICES, body(publish=True)).status_code == 403
    other = cse_admin.post(
        NOTICES, body(scope="DEPARTMENT", department_id=dept(world, "MECH"), publish=True)
    )
    not_found(other)
    # A department of another college can't be named either.
    foreign = str(world.river.departments["CSE"].id)
    not_found(cse_admin.post(NOTICES, body(scope="DEPARTMENT", department_id=foreign)))
    assert ids(world.browser("admin").get(NOTICES)) == []  # none of the above left anything
    assert create(cse_admin, scope="DEPARTMENT", department_id=dept(world, "CSE"), publish=True)


def test_a_college_admin_can_publish_for_any_department(world: World) -> None:
    created = create(
        world.browser("admin"), scope="DEPARTMENT", department_id=dept(world, "MECH"), publish=True
    )
    assert created["department"]["code"] == "MECH"
    assert ids(world.browser("mech_student").get(NOTICES)) == [created["id"]]


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "DEPARTMENT"},  # a department notice needs a department
        {"department_id": "00000000-0000-4000-8000-000000000001"},  # a college notice takes none
        {"title": "  "},
        {"title": "x" * 151},
        {"body": ""},
        {"body": "x" * 10_001},
        {"category": "SPORTS"},
        {"priority": "CRITICAL"},
        {"title": "bad\x00title"},
    ],
)
def test_invalid_notices_are_refused(world: World, change: dict[str, Any]) -> None:
    assert world.browser("admin").post(NOTICES, body(**change)).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"publish_at": "2030-01-01T00:00:00Z"},  # scheduled publishing: P1, deferred (P-9)
        {"audience": "STUDENT"},  # audience by kind: P1, deferred
        {"college_id": "00000000-0000-4000-8000-000000000001"},
        {"status": "PUBLISHED"},
        {"author_membership_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_clients_cannot_set_what_the_server_decides(world: World, extra: dict[str, Any]) -> None:
    response = world.browser("admin").post(NOTICES, body(**extra))
    assert response.status_code == 422
    assert ids(world.browser("admin").get(NOTICES, status="DRAFT")) == []


def test_the_body_is_stored_as_markdown_text_with_normalised_newlines(world: World) -> None:
    created = create(world.browser("admin"), body="line one\r\n\r\n* a\r\n* b  ")
    assert created["body"] == "line one\n\n* a\n* b"


# --- drafts, publishing and withdrawing ---


def test_drafts_are_private_to_the_people_who_may_manage_them(world: World) -> None:
    draft = create(
        world.browser("dept_admin"), scope="DEPARTMENT", department_id=dept(world, "CSE")
    )
    assert draft["status"] == "DRAFT" and draft["published_at"] is None

    for who in ("student", "faculty", "mech_student", "mech_admin"):
        reader = world.browser(who)
        assert ids(reader.get(NOTICES)) == [], who
        assert ids(reader.get(NOTICES, status="DRAFT")) == [], who
        refused = reader.get(f"{NOTICES}/{draft['id']}")
        not_found(refused)
        assert "Exam timetable" not in refused.text
    assert ids(world.browser("dept_admin").get(NOTICES, status="DRAFT")) == [draft["id"]]
    assert ids(world.browser("admin").get(NOTICES, status="DRAFT")) == [draft["id"]]


def test_publishing_a_draft_makes_it_visible_and_can_happen_once(world: World) -> None:
    admin = world.browser("admin")
    draft = create(admin)
    publish = f"{NOTICES}/{draft['id']}/publish"

    assert admin.post(publish, {"version": draft["version"]}).status_code == 200
    assert ids(world.browser("student").get(NOTICES)) == [draft["id"]]
    again = admin.post(publish, {"version": draft["version"] + 1})
    assert again.status_code == 409 and error_of(again)["code"] == "invalid_transition"


def test_only_managers_can_publish_a_draft(world: World) -> None:
    draft = create(world.browser("admin"))
    assert (
        world.browser("student")
        .post(f"{NOTICES}/{draft['id']}/publish", {"version": 1})
        .status_code
        == 404
    )
    published = create(world.browser("admin"), publish=True)
    assert (
        world.browser("student")
        .post(f"{NOTICES}/{published['id']}/publish", {"version": 1})
        .status_code
        == 403
    )


def test_a_notice_that_expired_while_in_draft_cannot_be_published(
    world: World, clock: Clock
) -> None:
    admin = world.browser("admin")
    expires = (clock.now + timedelta(hours=1)).isoformat()
    draft = create(admin, expires_at=expires)
    clock.advance(hours=2)
    response = admin.post(f"{NOTICES}/{draft['id']}/publish", {"version": 1})
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "expires_at"


def test_an_expiry_in_the_past_is_refused(world: World, clock: Clock) -> None:
    past = (clock.now - timedelta(minutes=1)).isoformat()
    response = world.browser("admin").post(NOTICES, body(expires_at=past))
    assert response.status_code == 422
    assert error_of(response)["details"][0]["field"] == "expires_at"


def test_editing_a_published_notice_records_the_update_and_audits_it(
    world: World, conn: Connection, clock: Clock
) -> None:
    admin = world.browser("admin")
    published = create(admin, publish=True)
    clock.advance(minutes=5)
    edited = admin.patch(
        f"{NOTICES}/{published['id']}",
        {"version": published["version"], "title": "Exam timetable (revised)", "priority": "HIGH"},
    )
    assert edited.status_code == 200, edited.text
    result = edited.json()
    assert result["title"] == "Exam timetable (revised)" and result["priority"] == "HIGH"
    assert result["version"] == published["version"] + 1 and result["edited_at"] is not None
    seen = world.browser("student").get(f"{NOTICES}/{published['id']}").json()
    assert seen["edited_at"] == result["edited_at"]
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log WHERE action = 'notice.updated' "
            "AND college_id = :c AND metadata -> 'fields' = '[\"priority\", \"title\"]'::jsonb",
            c=world.north.id,
        )
        == 1
    )


def test_editing_a_draft_does_not_claim_an_update(world: World) -> None:
    admin = world.browser("admin")
    draft = create(admin)
    result = admin.patch(f"{NOTICES}/{draft['id']}", {"version": 1, "body": "Changed."}).json()
    assert result["body"] == "Changed." and result["edited_at"] is None and result["version"] == 2


def test_the_expiry_can_be_changed_and_cleared(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    notice = create(admin, expires_at=(clock.now + timedelta(days=1)).isoformat())
    cleared = admin.patch(f"{NOTICES}/{notice['id']}", {"version": 1, "expires_at": None})
    assert cleared.status_code == 200 and cleared.json()["expires_at"] is None


def test_an_edit_based_on_an_old_version_is_refused(world: World) -> None:
    admin = world.browser("admin")
    draft = create(admin)
    assert (
        admin.patch(f"{NOTICES}/{draft['id']}", {"version": 1, "title": "First"}).status_code == 200
    )
    stale = admin.patch(f"{NOTICES}/{draft['id']}", {"version": 1, "title": "Second"})
    assert stale.status_code == 409 and error_of(stale)["code"] == "version_conflict"
    assert admin.get(f"{NOTICES}/{draft['id']}").json()["title"] == "First"


@pytest.mark.parametrize(
    "change", [{}, {"title": None}, {"scope": "DEPARTMENT"}, {"status": "DRAFT"}]
)
def test_edits_must_change_something_allowed(world: World, change: dict[str, Any]) -> None:
    admin = world.browser("admin")
    draft = create(admin)
    assert admin.patch(f"{NOTICES}/{draft['id']}", {"version": 1, **change}).status_code == 422


def test_who_may_edit_which_notice(world: World) -> None:
    cse = create(
        world.browser("dept_admin"),
        scope="DEPARTMENT",
        department_id=dept(world, "CSE"),
        publish=True,
    )
    college = create(world.browser("admin"), publish=True)
    edit = {"version": 2, "title": "Hijacked"}

    assert world.browser("student").patch(f"{NOTICES}/{cse['id']}", edit).status_code == 403
    not_found(
        world.browser("mech_admin").patch(f"{NOTICES}/{cse['id']}", edit)
    )  # can't even see it
    # A department admin can read a college notice but not change it.
    assert world.browser("dept_admin").patch(f"{NOTICES}/{college['id']}", edit).status_code == 403
    # Any college admin can edit; so can the department's own admin on its notice.
    assert world.browser("admin").patch(f"{NOTICES}/{cse['id']}", edit).status_code == 200
    assert (
        world.browser("dept_admin")
        .patch(f"{NOTICES}/{cse['id']}", {"version": 3, "title": "Mine"})
        .status_code
        == 200
    )
    assert (
        world.browser("admin").get(f"{NOTICES}/{college['id']}").json()["title"] == "Exam timetable"
    )


def test_an_author_who_lost_the_role_can_no_longer_edit(world: World, session: Session) -> None:
    from sqlalchemy import delete

    from app.models import RoleGrant

    cse = create(
        world.browser("dept_admin"),
        scope="DEPARTMENT",
        department_id=dept(world, "CSE"),
        publish=True,
    )
    session.execute(
        delete(RoleGrant).where(RoleGrant.membership_id == world.members["dept_admin"].id)
    )
    session.commit()
    author = world.browser("dept_admin")
    assert author.get(f"{NOTICES}/{cse['id']}").status_code == 200  # still a CSE member: can read
    assert author.patch(f"{NOTICES}/{cse['id']}", {"version": 2, "title": "x"}).status_code == 403


def test_withdrawing_needs_a_reason_and_hides_the_notice_from_readers(
    world: World, conn: Connection
) -> None:
    admin = world.browser("admin")
    published = create(admin, publish=True)
    withdraw = f"{NOTICES}/{published['id']}/withdraw"

    assert admin.post(withdraw, {}).status_code == 422
    assert admin.post(withdraw, {"reason": ""}).status_code == 422
    assert admin.post(withdraw, {"reason": "Posted to the wrong college"}).status_code == 200

    student = world.browser("student")
    assert ids(student.get(NOTICES)) == []
    not_found(student.get(f"{NOTICES}/{published['id']}"))
    assert ids(admin.get(NOTICES, status="WITHDRAWN")) == [published["id"]]
    assert ids(admin.get(NOTICES)) == []
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log WHERE action = 'notice.withdrawn' "
            "AND reason = 'Posted to the wrong college' AND college_id = :c",
            c=world.north.id,
        )
        == 1
    )
    again = admin.post(withdraw, {"reason": "again"})
    assert again.status_code == 409 and error_of(again)["code"] == "invalid_transition"
    gone = admin.patch(f"{NOTICES}/{published['id']}", {"version": 3, "title": "Back"})
    assert gone.status_code == 409


def test_only_published_notices_can_be_withdrawn_and_only_by_managers(world: World) -> None:
    admin = world.browser("admin")
    draft = create(admin)
    assert admin.post(f"{NOTICES}/{draft['id']}/withdraw", {"reason": "x"}).status_code == 409
    published = create(admin, publish=True)
    assert (
        world.browser("student")
        .post(f"{NOTICES}/{published['id']}/withdraw", {"reason": "x"})
        .status_code
        == 403
    )


def test_every_step_is_audited_without_the_notice_text(world: World, conn: Connection) -> None:
    admin = world.browser("admin")
    published = create(admin, title="Secret fee waiver details", publish=True)
    admin.post(f"{NOTICES}/{published['id']}/withdraw", {"reason": "mistake"})
    rows = conn.exec_driver_sql(
        "SELECT action, metadata::text FROM audit_log "
        "WHERE action LIKE 'notice.%%' ORDER BY created_at"
    ).all()
    assert [r[0] for r in rows] == ["notice.created", "notice.published", "notice.withdrawn"]
    assert all("Secret fee waiver" not in r[1] for r in rows)


# --- the list ---


def test_urgent_notices_are_pinned_first_then_newest_first(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    urgent = create(admin, priority="URGENT", title="Urgent", publish=True)
    clock.advance(minutes=1)
    older = create(admin, title="Older", publish=True)
    clock.advance(minutes=1)
    newer = create(admin, title="Newer", publish=True)

    listed = world.browser("student").get(NOTICES).json()["items"]
    assert [n["id"] for n in listed] == [urgent["id"], newer["id"], older["id"]]
    assert [n["pinned"] for n in listed] == [True, False, False]


def test_an_expired_notice_moves_to_past_notices_and_unpins(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    expiring = create(
        admin,
        priority="URGENT",
        expires_at=(clock.now + timedelta(hours=1)).isoformat(),
        publish=True,
    )
    lasting = create(admin, title="Lasting", publish=True)
    student = world.browser("student")
    assert ids(student.get(NOTICES)) == [expiring["id"], lasting["id"]]
    assert ids(student.get(NOTICES, past="true")) == []

    clock.advance(hours=2)
    assert ids(student.get(NOTICES)) == [lasting["id"]]
    past = student.get(NOTICES, past="true").json()["items"]
    assert [(n["id"], n["expired"], n["pinned"]) for n in past] == [(expiring["id"], True, False)]
    assert student.get(f"{NOTICES}/{expiring['id']}").status_code == 200  # still readable


def test_the_list_pages_with_a_cursor_without_gaps_or_repeats(world: World, clock: Clock) -> None:
    admin = world.browser("admin")
    expected: list[str] = []
    expected.append(create(admin, priority="URGENT", publish=True)["id"])
    clock.advance(seconds=1)
    for _ in range(5):
        clock.advance(seconds=1)
        expected.insert(1, create(admin, publish=True)["id"])  # newest first after the pin

    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = world.browser("student").get(NOTICES, **params).json()
        seen += [n["id"] for n in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == expected


def test_a_malformed_cursor_is_refused(world: World) -> None:
    response = world.browser("student").get(NOTICES, cursor="not-a-cursor")
    assert response.status_code == 422


def test_the_list_filters_by_category_and_department(world: World) -> None:
    admin = world.browser("admin")
    exam = create(admin, category="EXAMINATION", publish=True)
    event = create(admin, category="EVENT", publish=True)
    cse = create(
        admin,
        category="GENERAL",
        scope="DEPARTMENT",
        department_id=dept(world, "CSE"),
        publish=True,
    )
    student = world.browser("student")
    assert ids(student.get(NOTICES, category="EVENT")) == [event["id"]]
    assert set(ids(student.get(NOTICES, category="EXAMINATION"))) == {exam["id"]}
    assert ids(student.get(NOTICES, department_id=dept(world, "CSE"))) == [cse["id"]]
    # Filtering by a department the reader can't see yields nothing, not an error.
    assert ids(student.get(NOTICES, department_id=dept(world, "MECH"))) == []
    assert ids(student.get(NOTICES, department_id=str(world.river.departments["CSE"].id))) == []
    assert student.get(NOTICES, category="SPORTS").status_code == 422


def test_lists_and_single_reads_agree_for_every_reader(world: World) -> None:
    """The list must never show a notice the direct read refuses, nor hide one it allows."""
    admin, dept_admin = world.browser("admin"), world.browser("dept_admin")
    mech_admin = world.browser("mech_admin")
    made: list[dict[str, Any]] = []
    for author, scope, code in (
        (admin, "COLLEGE", None),
        (dept_admin, "DEPARTMENT", "CSE"),
        (mech_admin, "DEPARTMENT", "MECH"),
    ):
        extra = {"scope": scope, **({"department_id": dept(world, code)} if code else {})}
        made.append(create(author, **extra))  # draft
        made.append(create(author, publish=True, **extra))
        withdrawn = create(author, publish=True, **extra)
        assert (
            author.post(f"{NOTICES}/{withdrawn['id']}/withdraw", {"reason": "r"}).status_code == 200
        )
        made.append(withdrawn)

    for who in (*EVERYONE, "mech_admin", "river_student"):
        reader = world.browser(who)
        by_list: set[str] = set()
        for status in ("DRAFT", "PUBLISHED", "WITHDRAWN"):
            by_list |= set(ids(reader.get(NOTICES, status=status)))
            by_list |= set(ids(reader.get(NOTICES, status=status, past="true")))
        by_get = {n["id"] for n in made if reader.get(f"{NOTICES}/{n['id']}").status_code == 200}
        assert by_list == by_get, who


# --- department pages (DEPT-003/004) ---


def test_a_department_page_shows_its_admins_by_name_only(world: World) -> None:
    page = world.browser("student").get(f"{CAMPUS}/departments/{dept(world, 'CSE')}").json()
    assert page["admins"] == ["Dept Admin"]
    assert set(page) == {"id", "code", "name", "description", "archived", "admins"}
    mech = world.browser("student").get(f"{CAMPUS}/departments/{dept(world, 'MECH')}").json()
    assert mech["admins"] == ["Mech Admin"]


def test_a_department_admin_edits_only_their_own_departments_description(
    world: World, conn: Connection
) -> None:
    cse_admin = world.browser("dept_admin")
    mine = f"{CAMPUS}/departments/{dept(world, 'CSE')}"
    other = f"{CAMPUS}/departments/{dept(world, 'MECH')}"

    ok = cse_admin.patch(mine, {"description": "Labs in block C."})
    assert ok.status_code == 200 and ok.json()["description"] == "Labs in block C."
    not_found(cse_admin.patch(other, {"description": "Mine now"}))
    assert cse_admin.patch(mine, {"name": "Renamed"}).status_code == 403
    assert cse_admin.patch(mine, {"archived": True}).status_code == 403
    assert world.browser("student").patch(mine, {"description": "x"}).status_code == 403
    assert world.browser("faculty").patch(mine, {"description": "x"}).status_code == 403
    assert world.browser("admin").get(other).json()["description"] == ""
    assert (
        scalar(
            conn,
            "SELECT count(*) FROM audit_log "
            "WHERE action = 'college.department_updated' AND college_id = :c",
            c=world.north.id,
        )
        == 1
    )
