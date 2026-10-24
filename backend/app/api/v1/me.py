"""The signed-in user (architecture.md §11.1)."""

from fastapi import APIRouter, Depends, Response

from app.api.cookies import set_session_cookies
from app.api.deps import AppSettings, Auth, Db, Now, no_store
from app.models import MembershipStatus
from app.policies.campus import capabilities
from app.repositories.memberships import current_membership_view
from app.schemas.auth import ChangePasswordRequest, MeResponse, PasswordChangedResponse, UserOut
from app.schemas.campus import membership_out, roles_out
from app.schemas.membership import (
    CollegeListing,
    JoinResult,
    MembershipRequestCreate,
    MyRequestOut,
    MyRequests,
)
from app.services import auth as auth_service
from app.services import membership_requests

router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(no_store)])


@router.get("")
def me(auth: Auth, db: Db) -> MeResponse:
    view = current_membership_view(db, auth.user.id)
    if view is None:
        return MeResponse(
            user=UserOut.from_user(auth.user),
            capabilities=capabilities(auth.user, None, None, ()),
        )
    active = view.membership.status == MembershipStatus.ACTIVE
    return MeResponse(
        user=UserOut.from_user(auth.user),
        membership=membership_out(view),
        roles=roles_out(view) if active else [],
        capabilities=capabilities(auth.user, view.membership, view.college, view.grants),
    )


@router.post("/password")
def change_password(
    body: ChangePasswordRequest,
    auth: Auth,
    response: Response,
    db: Db,
    settings: AppSettings,
    now: Now,
) -> PasswordChangedResponse:
    issued = auth_service.change_password(
        db,
        settings,
        user=auth.user,
        current_password=body.current_password,
        new_password=body.new_password,
        now=now,
    )
    set_session_cookies(response, settings, issued)
    return PasswordChangedResponse(csrf_token=issued.csrf_token)


@router.post(
    "/membership-requests",
    status_code=202,
    response_model=JoinResult,
    response_model_exclude_none=True,
    responses={201: {"model": JoinResult, "description": "Joined at once (roster match)"}},
)
def request_membership(
    body: MembershipRequestCreate, auth: Auth, db: Db, now: Now, response: Response
) -> JoinResult:
    result = membership_requests.request_membership(
        db, user=auth.user, college_slug=body.college_slug, roll_number=body.roll_number, now=now
    )
    if not result.activated:
        # MEMBER-004: the same answer whatever the reason, so roll numbers can't be probed.
        return JoinResult(
            status="PENDING", message=f"Request sent. {result.college.name} will review it."
        )
    response.status_code = 201
    view = current_membership_view(db, auth.user.id)
    return JoinResult(
        status="ACTIVE",
        message=f"You've joined {result.college.name}.",
        membership=membership_out(view) if view else None,
    )


@router.get("/membership-requests")
def my_membership_requests(auth: Auth, db: Db) -> MyRequests:
    return MyRequests(
        items=[
            MyRequestOut(
                id=m.id,
                college=CollegeListing(name=c.name, slug=c.slug),
                status=m.status,  # type: ignore[arg-type]  # PENDING or REJECTED by the query
                decision_reason=m.decision_reason,
                created_at=m.created_at,
            )
            for m, c in membership_requests.my_requests(db, auth.user)
        ]
    )
