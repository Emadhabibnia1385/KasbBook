"""One account reached from every platform — and never two.

These tests encode the rule the whole product rests on: a transaction recorded
in Telegram is the same transaction the web panel shows, because both resolve to
the same internal user.
"""

from __future__ import annotations

import pytest

from kasbbook.modules.identity.models import LinkDirection, Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.shared.errors import AlreadyLinked, IdentityTakenError, InvalidLinkToken
from kasbbook.shared.security import token_digest

pytestmark = pytest.mark.asyncio


async def make_user(session, name="کاربر", email=None, password=None):
    service = IdentityService(session)
    user = await service.create_user(name, email=email, password=password)
    return service, user


# ------------------------------------------------------------------ accounts
async def test_internal_id_is_a_uuid_not_a_messenger_id(session):
    import uuid

    _, user = await make_user(session)
    assert isinstance(user.id, uuid.UUID)


async def test_password_is_never_stored_in_the_clear(session):
    _, user = await make_user(session, email="a@b.c", password="hunter2-hunter2")
    assert user.password_hash is not None
    assert "hunter2" not in user.password_hash
    assert user.password_hash.startswith("$argon2")


async def test_authenticate_accepts_the_right_password_only(session):
    service, _ = await make_user(session, email="a@b.c", password="hunter2-hunter2")
    assert await service.authenticate("a@b.c", "hunter2-hunter2") is not None
    assert await service.authenticate("a@b.c", "wrong") is None
    assert await service.authenticate("nobody@b.c", "hunter2-hunter2") is None


# --------------------------------------------------------- linking from web
async def test_web_issues_a_link_that_telegram_redeems(session):
    service, user = await make_user(session)

    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)
    assert issued.direction is LinkDirection.FROM_WEB

    identity = await service.complete_link_from_messenger(
        issued.token, Provider.TELEGRAM, "555001", external_username="emad"
    )
    assert identity.user_id == user.id
    assert identity.provider is Provider.TELEGRAM

    found = await service.user_for_identity(Provider.TELEGRAM, "555001")
    assert found is not None and found.id == user.id


async def test_a_link_token_is_single_use(session):
    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)

    await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "1")
    with pytest.raises(InvalidLinkToken):
        await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "2")


async def test_only_the_digest_of_a_link_token_is_stored(session):
    from sqlalchemy import select

    from kasbbook.modules.identity.models import LinkToken

    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.BALE)

    rows = (await session.execute(select(LinkToken))).scalars().all()
    assert len(rows) == 1
    assert rows[0].token_digest != issued.token
    assert rows[0].token_digest == token_digest(issued.token)


async def test_a_telegram_link_cannot_be_redeemed_from_bale(session):
    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)

    with pytest.raises(InvalidLinkToken):
        await service.complete_link_from_messenger(issued.token, Provider.BALE, "999")


async def test_an_expired_link_is_refused(session):
    from sqlalchemy import select

    from kasbbook.modules.identity.models import LinkToken
    from kasbbook.shared.security import expires_in

    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)

    record = (await session.execute(select(LinkToken))).scalar_one()
    record.expires_at = expires_in(-1)
    await session.flush()

    with pytest.raises(InvalidLinkToken):
        await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "1")


async def test_a_revoked_link_is_refused(session):
    from sqlalchemy import select

    from kasbbook.modules.identity.models import LinkToken

    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)

    record = (await session.execute(select(LinkToken))).scalar_one()
    await service.revoke_link(record.id, user.id)

    with pytest.raises(InvalidLinkToken):
        await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "1")


# --------------------------------------------------- linking from messenger
async def test_messenger_issues_a_code_the_web_redeems(session):
    service, user = await make_user(session)

    issued = await service.start_link_from_messenger(Provider.RUBIKA, "rub-7", "emad")
    assert issued.direction is LinkDirection.FROM_MESSENGER
    assert issued.token.isupper() and len(issued.token) == 8

    identity = await service.complete_link_from_web(issued.token, user.id)
    assert identity.user_id == user.id
    assert identity.provider is Provider.RUBIKA
    assert identity.external_id == "rub-7"


async def test_a_messenger_code_cannot_be_redeemed_by_a_messenger(session):
    service, user = await make_user(session)
    issued = await service.start_link_from_messenger(Provider.RUBIKA, "rub-7")

    with pytest.raises(InvalidLinkToken):
        await service.complete_link_from_messenger(issued.token, Provider.RUBIKA, "rub-7")


# -------------------------------------------------------------- the big rule
async def test_one_identity_never_belongs_to_two_accounts(session):
    service = IdentityService(session)
    first = await service.create_user("اول")
    second = await service.create_user("دوم")

    issued = await service.start_link_from_web(first.id, Provider.TELEGRAM)
    await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")

    stolen = await service.start_link_from_web(second.id, Provider.TELEGRAM)
    with pytest.raises(IdentityTakenError):
        await service.complete_link_from_messenger(stolen.token, Provider.TELEGRAM, "555001")

    # The first account still owns it.
    owner = await service.user_for_identity(Provider.TELEGRAM, "555001")
    assert owner.id == first.id


async def test_relinking_the_same_identity_to_the_same_account_is_rejected(session):
    service, user = await make_user(session)

    first = await service.start_link_from_web(user.id, Provider.EITAA)
    await service.complete_link_from_messenger(first.token, Provider.EITAA, "eit-1")

    again = await service.start_link_from_web(user.id, Provider.EITAA)
    with pytest.raises(AlreadyLinked):
        await service.complete_link_from_messenger(again.token, Provider.EITAA, "eit-1")


async def test_a_messenger_already_linked_cannot_start_a_new_link(session):
    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.BALE)
    await service.complete_link_from_messenger(issued.token, Provider.BALE, "bale-9")

    with pytest.raises(AlreadyLinked):
        await service.start_link_from_messenger(Provider.BALE, "bale-9")


# ------------------------------------------------ all four on one account
async def test_all_four_messengers_resolve_to_one_account(session):
    service, user = await make_user(session, "عماد")

    externals = {
        Provider.TELEGRAM: "tg-1",
        Provider.BALE: "bale-1",
        Provider.RUBIKA: "rub-1",
        Provider.EITAA: "eit-1",
    }
    for provider, external in externals.items():
        issued = await service.start_link_from_web(user.id, provider)
        await service.complete_link_from_messenger(issued.token, provider, external)

    identities = await service.list_identities(user.id)
    assert len(identities) == 4

    for provider, external in externals.items():
        resolved = await service.user_for_identity(provider, external)
        assert resolved.id == user.id, f"{provider} did not resolve to the one account"


async def test_unlinking_frees_the_identity_for_another_account(session):
    service = IdentityService(session)
    first = await service.create_user("اول")
    second = await service.create_user("دوم")

    issued = await service.start_link_from_web(first.id, Provider.TELEGRAM)
    identity = await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "tg-x")

    await service.unlink(first.id, identity.id)
    assert await service.user_for_identity(Provider.TELEGRAM, "tg-x") is None

    moved = await service.start_link_from_web(second.id, Provider.TELEGRAM)
    now = await service.complete_link_from_messenger(moved.token, Provider.TELEGRAM, "tg-x")
    assert now.user_id == second.id


async def test_unlinking_someone_elses_identity_is_refused(session):
    from kasbbook.shared.errors import NotFound

    service = IdentityService(session)
    owner = await service.create_user("مالک")
    stranger = await service.create_user("غریبه")

    issued = await service.start_link_from_web(owner.id, Provider.TELEGRAM)
    identity = await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "tg-y")

    with pytest.raises(NotFound):
        await service.unlink(stranger.id, identity.id)


async def test_linking_is_audited(session):
    from sqlalchemy import select

    from kasbbook.modules.identity.models import AuditEvent

    service, user = await make_user(session)
    issued = await service.start_link_from_web(user.id, Provider.TELEGRAM)
    await service.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "tg-1")

    actions = [
        row.action for row in (await session.execute(select(AuditEvent))).scalars().all()
    ]
    assert "user.created" in actions
    assert "link.started" in actions
    assert "identity.linked" in actions
