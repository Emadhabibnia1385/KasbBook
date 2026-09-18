"""An invitation grants only its recipient the right to accept or decline."""

import uuid
from typing import List

from fastapi import APIRouter

from ...modules.books.invitations import InvitationService
from ..deps import CurrentUser, SessionDep
from ..schemas import InvitationReply, InvitationResponse

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.get("", response_model=List[InvitationResponse])
async def incoming(user: CurrentUser, session: SessionDep):
    return await InvitationService(session).incoming(user.id)


@router.post("/{invitation_id}/respond", response_model=InvitationResponse)
async def respond(invitation_id: uuid.UUID, body: InvitationReply, user: CurrentUser, session: SessionDep):
    return await InvitationService(session).respond(invitation_id, user.id, body.accept)
