"""Post-commit delivery shared by polling, webhooks and background invitations."""

import logging

from ..adapters.base import OutgoingMessage
from ..modules.books.invitations import InvitationService
from . import screens

logger = logging.getLogger("kasbbook.delivery")


async def deliver_notifications(adapter, reply):
    for notification in reply.notifications:
        try:
            if not await adapter.send_message(notification):
                logger.warning("login proof delivery refused")
        except Exception:
            # Keep the requester response identical to an unknown destination.
            # Raw codes are not logged, stored in state, or queued for retries.
            logger.warning("login proof delivery failed")


async def deliver_invitations(session, adapter, provider=None):
    service = InvitationService(session)
    sent = 0
    for invitation, identity, book in await service.pending_delivery(provider or adapter.provider):
        text, buttons = screens.team_invitation(book, invitation)
        try:
            if await adapter.send_message(OutgoingMessage(identity.external_id, text, buttons)):
                await service.mark_delivered(invitation)
                sent += 1
        except Exception:
            logger.warning("invitation delivery failed; retained for retry")
    await session.flush()
    return sent
