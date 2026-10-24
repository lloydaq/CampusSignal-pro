"""Membership and college shapes (architecture.md §11.1). Responses whitelist their fields:
roster details, verification flags and decision internals are never included here."""

import uuid
from typing import Self

from pydantic import BaseModel

from app.models import College, Department
from app.repositories.memberships import MembershipView


class CollegeOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    status: str
    is_demo: bool

    @classmethod
    def from_college(cls, college: College) -> Self:
        return cls(
            id=college.id,
            name=college.name,
            slug=college.slug,
            timezone=college.timezone,
            status=college.status,
            is_demo=college.is_demo,
        )


class DepartmentRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str

    @classmethod
    def from_department(cls, department: Department) -> Self:
        return cls(id=department.id, code=department.code, name=department.name)


class MembershipOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    college: CollegeOut
    department: DepartmentRef | None


class RoleOut(BaseModel):
    role: str
    department: DepartmentRef | None


def membership_out(view: MembershipView) -> MembershipOut:
    return MembershipOut(
        id=view.membership.id,
        kind=view.membership.kind,
        status=view.membership.status,
        college=CollegeOut.from_college(view.college),
        # A pending request's department comes from a roster match; showing it would tell the
        # requester whether their roll number exists (MEMBER-004).
        department=DepartmentRef.from_department(view.department)
        if view.department and view.membership.status != "PENDING"
        else None,
    )


def roles_out(view: MembershipView) -> list[RoleOut]:
    return [
        RoleOut(
            role=g.role,
            department=DepartmentRef.from_department(view.grant_departments[g.department_id])
            if g.department_id
            else None,
        )
        for g in view.grants
    ]
