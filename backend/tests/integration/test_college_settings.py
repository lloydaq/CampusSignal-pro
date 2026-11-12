# ruff: noqa: F811  (fixtures imported from test_attendance are redefined as parameters)
"""College settings (ACADEMIC-006, P-5): the attendance edit window is configurable per college
by its college admins, audited with the old and new value, and used for every session at once.
"""

from typing import Any

import pytest
from sqlalchemy import Connection

from tests.integration.auth_helpers import error_of
from tests.integration.campus_world import CAMPUS, World
from tests.integration.conftest import Clock
from tests.integration.test_attendance import cs, marks, ok, record, world  # noqa: F401

pytestmark = pytest.mark.integration

SETTINGS = f"{CAMPUS}/settings"


def test_college_admins_read_and_change_the_edit_window(
    world: World, cs: dict[str, Any], conn: Connection, clock: Clock
) -> None:
    admin = world.browser("admin")
    assert ok(admin.get(SETTINGS)) == {"attendance_edit_window_hours": 48}
    changed = ok(admin.patch(SETTINGS, {"attendance_edit_window_hours": 24}))
    assert changed == {"attendance_edit_window_hours": 24}
    reason, data = conn.exec_driver_sql(
        "SELECT reason, metadata::text FROM audit_log WHERE action = 'college.settings_changed'"
    ).one()
    assert reason is None and '"from": 48' in data and '"to": 24' in data

    # Faculty now get 24 hours, for sessions already recorded too.
    session = ok(record(world, cs), 201)
    assert session["edit_window_closes_at"] == "2026-10-22T12:00:00Z"
    clock.advance(hours=25)
    late = world.browser("faculty").patch(
        f"{CAMPUS}/attendance-sessions/{session['id']}",
        {"version": 1, "records": marks(cs, student="ABSENT")},
    )
    assert late.status_code == 403 and error_of(late)["code"] == "edit_window_closed"


def test_the_window_stays_between_1_hour_and_30_days(world: World) -> None:
    admin = world.browser("admin")
    for bad in (0, 721, -5, "48", None):
        response = admin.patch(SETTINGS, {"attendance_edit_window_hours": bad})
        assert response.status_code == 422, bad
    assert admin.patch(SETTINGS, {"attendance_edit_window_hours": 48, "x": 1}).status_code == 422
    assert (
        ok(admin.patch(SETTINGS, {"attendance_edit_window_hours": 720}))[
            "attendance_edit_window_hours"
        ]
        == 720
    )


@pytest.mark.parametrize("who", ["dept_admin", "faculty", "student"])
def test_only_college_admins_change_settings(world: World, who: str) -> None:
    browser = world.browser(who)
    assert browser.patch(SETTINGS, {"attendance_edit_window_hours": 1}).status_code == 403
    assert browser.get(SETTINGS).status_code == 403
    assert ok(world.browser("admin").get(SETTINGS))["attendance_edit_window_hours"] == 48


def test_a_college_changes_only_its_own_settings(world: World) -> None:
    ok(world.browser("river_admin").patch(SETTINGS, {"attendance_edit_window_hours": 6}))
    assert ok(world.browser("admin").get(SETTINGS))["attendance_edit_window_hours"] == 48
