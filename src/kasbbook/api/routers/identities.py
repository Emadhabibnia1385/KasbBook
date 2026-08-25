"""Attaching and detaching messengers.

A KasbBook account is not a Telegram account. This is the seam where the two
meet, in both directions: the web starts a link and a messenger redeems it, or
a messenger starts one and the web claims it.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter

from ...modules.identity.models import MESSENGERS, Provider
from ...modules.identity.service import IdentityService
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep, SettingsDep
from ..schemas import (
    ClaimLinkRequest,
    IdentityResponse,
    StartLinkRequest,
    StartLinkResponse,
)

router = APIRouter(prefix="/identities", tags=["identities"])

DEEP_LINK_HOSTS = {
    Provider.TELEGRAM: "https://t.me/{username}?start={payload}",
    Provider.BALE: "https://ble.ir/{username}?start={payload}",
    Provider.RUBIKA: "https://rubika.ir/{username}?start={payload}",
}


@router.get("", response_model=List[IdentityResponse])
async def list_identities(user: CurrentUser, session: SessionDep) -> List[IdentityResponse]:
    rows = await IdentityService(session).list_identities(user.id)
    return [
        IdentityResponse(
            id=row.id, provider=row.provider.value, external_id=row.external_id,
            external_username=row.external_username, display_name=row.display_name,
            linked_at=row.linked_at,
        )
        for row in rows
    ]


@router.post("/link", response_model=StartLinkResponse, status_code=201)
async def start_link(
    body: StartLinkRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> StartLinkResponse:
    """Issue a one-time code, and a link that hands it to the bot directly."""
    try:
        provider = Provider(body.provider.lower())
    except ValueError:
        raise ValidationError(
            "provider must be one of: " + ", ".join(p.value for p in MESSENGERS)
        ) from None

    if provider not in MESSENGERS:
        raise ValidationError(f"{provider.value} is not a messenger")

    issued = await IdentityService(session).start_link_from_web(user.id, provider)

    username = getattr(settings, f"{provider.value}_bot_username", "")
    template = DEEP_LINK_HOSTS.get(provider)
    deep_link = (
        template.format(username=username, payload=issued.token)
        if template and username else None
    )
    return StartLinkResponse(
        token=issued.token, expires_at=issued.expires_at_iso, deep_link=deep_link
    )


@router.post("/claim", response_model=IdentityResponse, status_code=201)
async def claim_link(
    body: ClaimLinkRequest, user: CurrentUser, session: SessionDep
) -> IdentityResponse:
    """Redeem a code the messenger side produced, attaching it to this account."""
    identity = await IdentityService(session).complete_link_from_web(body.code, user.id)
    return IdentityResponse(
        id=identity.id, provider=identity.provider.value,
        external_id=identity.external_id, external_username=identity.external_username,
        display_name=identity.display_name, linked_at=identity.linked_at,
    )


@router.delete("/{identity_id}", status_code=204)
async def unlink(identity_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await IdentityService(session).unlink(user.id, identity_id)
