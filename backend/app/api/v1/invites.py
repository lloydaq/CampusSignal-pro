"""Accepting an invitation to a college (MEMBER-007, ADMIN-002, P-7).

The token travels in the request body, not the URL as first sketched in architecture.md
§11.1 (`/invites/{token}/accept`): paths reach access logs, bodies don't (Rules R-2.11).
"""

from fastapi import APIRouter, Depends, Request

from app.api.deps import Auth, Db, IpKey, Now, no_store
from app.core.errors import NotFound
from app.repositories.memberships import current_membership_view
from app.schemas.campus import membership_out
from app.schemas.platform import InviteAcceptRequest, InviteAcceptResponse
from app.services import invites as invite_service
from app.services.sessions import SESSION_COOKIE

router = APIRouter(prefix="/invites", tags=["invites"], dependencies=[Depends(no_store)])


@router.post("/accept")
def accept_invite(
    body: InviteAcceptRequest, request: Request, auth: Auth, db: Db, now: Now, ip_key: IpKey
) -> InviteAcceptResponse:
    invite_service.accept_invite(
        db,
        user=auth.user,
        token=body.token,
        session_token=request.cookies.get(SESSION_COOKIE),
        ip_key=ip_key,
        now=now,
    )
    view = current_membership_view(db, auth.user.id)
    if view is None:  # can't happen: the membership was just created or confirmed ACTIVE
        raise NotFound()
    return InviteAcceptResponse(membership=membership_out(view))
