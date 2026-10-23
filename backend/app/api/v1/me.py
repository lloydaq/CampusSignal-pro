"""The signed-in user (architecture.md §11.1)."""

from fastapi import APIRouter, Depends, Response

from app.api.cookies import set_session_cookies
from app.api.deps import AppSettings, Auth, Db, Now, no_store
from app.models import MembershipStatus
from app.policies.campus import capabilities
from app.repositories.memberships import current_membership_view
from app.schemas.auth import ChangePasswordRequest, MeResponse, PasswordChangedResponse, UserOut
from app.schemas.campus import membership_out, roles_out
from app.services import auth as auth_service

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
