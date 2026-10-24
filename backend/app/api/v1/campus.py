"""College administration routes (architecture.md §11.1). Every route takes its college from
`Campus` (the session's ACTIVE membership); the services load objects with that college id,
then apply the policies in app/policies/campus.py."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app.api.deps import AppSettings, Campus, Db, MailerDep, Now, no_store
from app.core.mailer import send_email
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.models import Department, MembershipKind, MembershipStatus, Role
from app.schemas.campus import DepartmentRef
from app.schemas.college_admin import (
    ActorRef,
    CollegeAuditEntry,
    CollegeAuditPage,
    DepartmentCreate,
    DepartmentList,
    DepartmentOut,
    DepartmentUpdate,
    GrantCreate,
    GrantOut,
    InviteCreate,
    InviteList,
    InviteOut,
    MemberOut,
    MemberPage,
    MemberUpdate,
    RosterEntryOut,
    RosterImport,
    RosterImported,
    RosterPage,
)
from app.services import college_audit, departments, members, roster
from app.services import invites as invite_service
from app.services.members import MemberRow
from app.services.platform import invite_state

router = APIRouter(prefix="/campus", tags=["campus"], dependencies=[Depends(no_store)])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorParam = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]


def _ref(department: Department | None) -> DepartmentRef | None:
    return DepartmentRef.from_department(department) if department else None


# --- departments ---------------------------------------------------------------------------


@router.get("/departments")
def list_departments(campus: Campus, db: Db, include_archived: bool = False) -> DepartmentList:
    rows = departments.list_departments(db, campus, include_archived=include_archived)
    return DepartmentList(items=[DepartmentOut.from_department(d) for d in rows])


@router.post("/departments", status_code=201)
def create_department(body: DepartmentCreate, campus: Campus, db: Db, now: Now) -> DepartmentOut:
    department = departments.create_department(
        db, campus, code=body.code, name=body.name, description=body.description, now=now
    )
    return DepartmentOut.from_department(department)


@router.get("/departments/{department_id}")
def get_department(department_id: uuid.UUID, campus: Campus, db: Db) -> DepartmentOut:
    return DepartmentOut.from_department(departments.get_department(db, campus, department_id))


@router.patch("/departments/{department_id}")
def update_department(
    department_id: uuid.UUID, body: DepartmentUpdate, campus: Campus, db: Db, now: Now
) -> DepartmentOut:
    department = departments.update_department(
        db,
        campus,
        department_id,
        name=body.name,
        description=body.description,
        archived=body.archived,
        now=now,
    )
    return DepartmentOut.from_department(department)


# --- roster --------------------------------------------------------------------------------


@router.post("/roster/import", status_code=201)
def import_roster(body: RosterImport, campus: Campus, db: Db, now: Now) -> RosterImported:
    return RosterImported(imported=roster.import_roster(db, campus, text=body.csv, now=now))


@router.get("/roster")
def list_roster(
    campus: Campus,
    db: Db,
    query: Search = None,
    department_id: uuid.UUID | None = None,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> RosterPage:
    rows, next_cursor = roster.list_roster(
        db,
        campus,
        query=query,
        department_id=department_id,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return RosterPage(
        items=[
            RosterEntryOut(
                id=r.entry.id,
                roll_number=r.entry.roll_number,
                full_name=r.entry.full_name,
                email=r.entry.email,
                program=r.entry.program,
                admission_year=r.entry.admission_year,
                department=DepartmentRef.from_department(r.department),
                claimed=r.claimed,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


# --- invites -------------------------------------------------------------------------------


@router.post("/invites", status_code=201)
def invite(
    body: InviteCreate,
    campus: Campus,
    background: BackgroundTasks,
    db: Db,
    settings: AppSettings,
    mailer: MailerDep,
    now: Now,
) -> InviteOut:
    created, email = invite_service.invite_member(
        db, settings, campus, email=body.email, kind=body.kind, now=now
    )
    background.add_task(send_email, mailer, email)
    return InviteOut.build(created, "PENDING")


@router.get("/invites")
def list_invites(campus: Campus, db: Db, now: Now) -> InviteList:
    rows = invite_service.pending_invites(db, campus, now)
    return InviteList(items=[InviteOut.build(i, invite_state(i, now)) for i in rows])


# --- members and roles ---------------------------------------------------------------------


def _member_out(row: MemberRow) -> MemberOut:
    return MemberOut(
        id=row.membership.id,
        user_id=row.user.id,
        display_name=row.user.display_name,
        kind=row.membership.kind,
        status=row.membership.status,
        department=_ref(row.department),
        email=row.user.email if row.show_contact else None,
        roll_number=row.roll_number,
        roles=[GrantOut(id=g.id, role=g.role, department=_ref(d)) for g, d in row.grants],
        joined_at=row.membership.created_at,
    )


@router.get("/members")
def list_members(
    campus: Campus,
    db: Db,
    query: Search = None,
    kind: MembershipKind | None = None,
    status: Annotated[
        MembershipStatus | None, Query(description="ACTIVE, SUSPENDED or ENDED")
    ] = None,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> MemberPage:
    rows, next_cursor = members.directory(
        db,
        campus,
        query=query,
        kind=kind,
        status=status,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return MemberPage(items=[_member_out(r) for r in rows], next_cursor=next_cursor)


@router.patch("/members/{membership_id}")
def update_member(
    membership_id: uuid.UUID, body: MemberUpdate, campus: Campus, db: Db, now: Now
) -> MemberOut:
    membership = members.update_member(
        db,
        campus,
        membership_id,
        department_id=body.department_id,
        status=body.status,
        reason=body.reason,
        now=now,
    )
    return _member_out(members.member_row(db, campus, membership))


@router.post("/members/{membership_id}/grants", status_code=201)
def grant_role(membership_id: uuid.UUID, body: GrantCreate, campus: Campus, db: Db) -> GrantOut:
    grant, department = members.grant_role(
        db, campus, membership_id, role=Role(body.role), department_id=body.department_id
    )
    return GrantOut(id=grant.id, role=grant.role, department=_ref(department))


@router.delete("/members/{membership_id}/grants/{grant_id}", status_code=204)
def revoke_role(membership_id: uuid.UUID, grant_id: uuid.UUID, campus: Campus, db: Db) -> Response:
    members.revoke_role(db, campus, membership_id, grant_id)
    return Response(status_code=204)


# --- audit ---------------------------------------------------------------------------------


@router.get("/audit-log")
def audit_log(
    campus: Campus,
    db: Db,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: CursorParam = None,
    limit: Limit = DEFAULT_LIMIT,
) -> CollegeAuditPage:
    rows, next_cursor = college_audit.college_audit(
        db,
        campus,
        action=action,
        actor_user_id=actor_user_id,
        since=since,
        until=until,
        cursor=decode_cursor(cursor),
        limit=limit,
    )
    return CollegeAuditPage(
        items=[
            CollegeAuditEntry.build(
                e, ActorRef(id=u.id, display_name=u.display_name) if u else None
            )
            for e, u in rows
        ],
        next_cursor=next_cursor,
    )
