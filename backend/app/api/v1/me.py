"""The signed-in user (architecture.md §11.1)."""

from fastapi import APIRouter, Depends, Response

from app.api.cookies import set_session_cookies
from app.api.deps import AppSettings, Auth, Db, Now, no_store
from app.schemas.auth import ChangePasswordRequest, MeResponse, PasswordChangedResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(no_store)])


@router.get("")
def me(auth: Auth) -> MeResponse:
    return MeResponse(user=UserOut.from_user(auth.user))


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
