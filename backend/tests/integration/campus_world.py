"""A populated two-college world for the college-admin and tenant-isolation tests.

Northfield Institute: a college admin (faculty), a CSE department admin (staff), a CSE faculty
member, two students (CSE, MECH) backed by roster entries. Riverside College: a college admin
and a student. Everyone's password is tenancy.PASSWORD.
"""

from dataclasses import dataclass, field

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.models import CollegeMembership, MembershipKind, Role, RosterEntry
from tests.integration.platform_helpers import Browser
from tests.integration.tenancy import Campus, add_member, make_user, roster_entry, two_colleges

CAMPUS = "/api/v1/campus"


@dataclass
class World:
    app: FastAPI
    north: Campus
    river: Campus
    members: dict[str, CollegeMembership] = field(default_factory=dict)
    roster: dict[str, RosterEntry] = field(default_factory=dict)

    def browser(self, who: str) -> Browser:
        return Browser(self.app, f"{who}@{self.domain(who)}")

    @staticmethod
    def domain(who: str) -> str:
        return "riverside.example" if who.startswith("river") else "northfield.example"


def build_world(session: Session, app: FastAPI) -> World:
    north, river = two_colleges(session)
    world = World(app, north, river)

    def member(
        who: str,
        campus: Campus,
        kind: MembershipKind,
        department: str | None,
        roles: tuple[tuple[Role, str | None], ...] = (),
    ) -> CollegeMembership:
        name = who.replace("_", " ").title()
        user = make_user(session, f"{who}@{World.domain(who)}", name=name)
        membership = add_member(session, user, campus, kind, department=department, roles=roles)
        world.members[who] = membership
        return membership

    member("admin", north, MembershipKind.FACULTY, "CSE", ((Role.COLLEGE_ADMIN, None),))
    member("dept_admin", north, MembershipKind.STAFF, "CSE", ((Role.DEPARTMENT_ADMIN, "CSE"),))
    member("faculty", north, MembershipKind.FACULTY, "CSE")
    for who, roll, department in (("student", "N-001", "CSE"), ("mech_student", "N-002", "MECH")):
        entry = roster_entry(
            session, north, roll, department=department, email=f"{who}@northfield.example"
        )
        world.roster[who] = entry
        member(who, north, MembershipKind.STUDENT, department).roster_entry_id = entry.id
    member("river_admin", river, MembershipKind.FACULTY, "CSE", ((Role.COLLEGE_ADMIN, None),))
    entry = roster_entry(session, river, "R-001", email="river_student@riverside.example")
    world.roster["river_student"] = entry
    member("river_student", river, MembershipKind.STUDENT, "CSE").roster_entry_id = entry.id
    session.commit()
    return world
