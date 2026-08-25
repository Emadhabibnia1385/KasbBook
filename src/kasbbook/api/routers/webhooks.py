"""Receiving updates over HTTP instead of polling for them.

The security question here is the only interesting one: how does this route
know the caller is really the provider? Telegram answers it — it echoes a
secret token in a header we registered. Bale and Rubika do not sign anything at
all, so for them the only defence is a URL nobody can guess.

So the path itself carries a secret, and it is compared in constant time. That
is weaker than a signature and this says so plainly rather than implying a
check that is not happening.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Request, Response, status

from ...modules.identity.models import Provider
from ..deps import SessionDep

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("kasbbook.api.webhooks")


@router.post("/{provider}/{secret}")
async def receive(
    provider: str, secret: str, request: Request, session: SessionDep
) -> Response:
    """One update from a provider.

    Always answers 200, even for an update that fails. A provider that gets an
    error retries, and retrying a poisoned update forever is worse than
    dropping it and logging the reason.
    """
    runtime = request.app.state
    adapter = getattr(runtime, "adapters", {}).get(provider)

    if adapter is None:
        # An unconfigured provider is indistinguishable from a wrong secret,
        # on purpose: neither should tell a prober which one they got wrong.
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    expected = getattr(runtime, "webhook_paths", {}).get(provider, "")
    if not expected or not hmac.compare_digest(secret, expected):
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    body = await request.body()
    if not adapter.verify_webhook(dict(request.headers), body):
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    payload = await request.json()
    event = adapter.parse_event(payload)
    if event is None:
        return Response(status_code=status.HTTP_200_OK)

    from ...bot.conversation import Conversation

    try:
        conversation = Conversation(session, runtime.state_store, Provider(provider))
        reply = await conversation.handle(event)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("webhook update failed; acknowledged anyway")
        return Response(status_code=status.HTTP_200_OK)

    if event.callback_id:
        await adapter.answer_callback(event.callback_id)

    if reply.edit_message_id:
        await adapter.edit_message(reply)
    else:
        await adapter.send_message(reply)

    return Response(status_code=status.HTTP_200_OK)
