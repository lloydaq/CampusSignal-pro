"""Authorization decisions for identity (Rules R-2.1: every decision lives in app/policies/)."""

from app.models.user import User, UserStatus


def can_sign_in(user: User) -> bool:
    """Only ACTIVE accounts may sign in or keep a session (AUTH-009).

    Evaluated at login and again on every request, so a suspension or deactivation takes
    effect on the user's next request rather than at their next sign-in.
    """
    return user.status == UserStatus.ACTIVE
