"""Authentication routes (architecture.md §11.1). Thin: parse, call the service, shape the reply."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.api.cookies import clear_session_cookies, set_csrf_cookie, set_session_cookies
from app.api.deps import (
    AppSettings,
    Auth,
    Db,
    IpKey,
    MailerDep,
    Now,
    OptionalAuth,
    no_store,
)
from app.core.mailer import send_email
from app.schemas.auth import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services import auth as auth_service
from app.services.sessions import SESSION_COOKIE, csrf_token_for

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(no_store)])

# The same text for new and existing emails, and for known and unknown reset addresses.
REGISTERED_MESSAGE = "Check your email to finish setting up your account."
RESET_REQUESTED_MESSAGE = "If an account exists for that email, we've sent a reset link."


@router.post("/register", status_code=201)
def register(
    body: RegisterRequest,
    background: BackgroundTasks,
    db: Db,
    settings: AppSettings,
    now: Now,
    mailer: MailerDep,
    ip_key: IpKey,
) -> MessageResponse:
    email = auth_service.register(
        db,
        settings,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        ip_key=ip_key,
        now=now,
    )
    if email is not None:
        background.add_task(send_email, mailer, email)
    return MessageResponse(message=REGISTERED_MESSAGE)


@router.post("/verify-email")
def verify_email(
    body: VerifyEmailRequest, request: Request, db: Db, now: Now, ip_key: IpKey
) -> MessageResponse:
    auth_service.verify_email(
        db,
        token=body.token,
        ip_key=ip_key,
        now=now,
        session_token=request.cookies.get(SESSION_COOKIE),
    )
    return MessageResponse(message="Your email is verified.")


@router.post("/resend-verification", status_code=202)
def resend_verification(
    auth: Auth,
    background: BackgroundTasks,
    db: Db,
    settings: AppSettings,
    now: Now,
    mailer: MailerDep,
) -> MessageResponse:
    email = auth_service.resend_verification(db, settings, user=auth.user, now=now)
    background.add_task(send_email, mailer, email)
    return MessageResponse(message="We've sent a new verification link.")


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: AppSettings,
    now: Now,
    ip_key: IpKey,
) -> LoginResponse:
    result = auth_service.login(
        db,
        settings,
        email=body.email,
        password=body.password,
        ip_key=ip_key,
        old_session_token=request.cookies.get(SESSION_COOKIE),
        now=now,
    )
    set_session_cookies(response, settings, result.session)
    return LoginResponse(user=UserOut.from_user(result.user), csrf_token=result.session.csrf_token)


@router.post("/logout", status_code=204)
def logout(auth: Auth, response: Response, db: Db, settings: AppSettings) -> None:
    auth_service.sign_out(db, session=auth.session)
    clear_session_cookies(response, settings)


@router.post("/logout-all", status_code=204)
def logout_all(auth: Auth, response: Response, db: Db, settings: AppSettings) -> None:
    auth_service.sign_out_everywhere(db, user=auth.user)
    clear_session_cookies(response, settings)


@router.get("/csrf")
def csrf(auth: OptionalAuth, response: Response, settings: AppSettings) -> CsrfResponse:
    """The CSRF token for the current session, or null when signed out."""
    if auth is None:
        return CsrfResponse(csrf_token=None)
    token = csrf_token_for(auth.session.csrf_secret)
    remaining = auth.session.expires_at - auth.session.created_at
    set_csrf_cookie(response, settings, token, int(remaining.total_seconds()))
    return CsrfResponse(csrf_token=token)


@router.post("/password-reset/request", status_code=202)
def request_password_reset(
    body: PasswordResetRequest,
    background: BackgroundTasks,
    db: Db,
    settings: AppSettings,
    now: Now,
    mailer: MailerDep,
    ip_key: IpKey,
) -> MessageResponse:
    email = auth_service.request_password_reset(
        db, settings, email=body.email, ip_key=ip_key, now=now
    )
    if email is not None:
        background.add_task(send_email, mailer, email)
    return MessageResponse(message=RESET_REQUESTED_MESSAGE)


@router.post("/password-reset/confirm")
def confirm_password_reset(
    body: PasswordResetConfirmRequest, db: Db, now: Now, ip_key: IpKey
) -> MessageResponse:
    auth_service.confirm_password_reset(
        db, token=body.token, new_password=body.new_password, ip_key=ip_key, now=now
    )
    return MessageResponse(message="Your password was changed. Sign in with your new password.")
