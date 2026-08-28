"""One account reached from every platform — and never two.

These tests encode the rule the whole product rests on: a transaction recorded
in Telegram is the same transaction the web panel shows, because both resolve to
the same internal user.
"""

from __future__ import annotations

import pytest

from kasbbook.modules.identity.models import LinkDirection, Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.shared.errors import (
    AlreadyLinked,
    IdentityTakenError,
    InvalidLinkToken,
    ValidationError,
)
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


# ==================================================== the account itself
#
# An account created from a messenger starts with no email, no phone and no
# password. That is survivable but not good: it cannot sign in to the API, a
# colleague cannot find it to add to a book, and losing the messenger loses the
# books — which is the exact thing the identity model exists to prevent.
# These cover the path out of that.

async def test_an_account_made_from_a_messenger_is_linked_in_one_go(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(
        Provider.TELEGRAM, "555001", display_name="عماد", external_username="emad"
    )

    assert user.display_name == "عماد"
    assert await identity.user_for_identity(Provider.TELEGRAM, "555001") is not None


async def test_a_messenger_that_already_belongs_somewhere_cannot_make_a_second(session):
    identity = IdentityService(session)
    await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    with pytest.raises(AlreadyLinked):
        await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")


async def test_a_new_account_starts_unreachable_and_that_is_the_point(session):
    """Stated as a test so the day it changes, somebody notices."""
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    assert user.email is None and user.phone is None
    assert user.password_hash is None
    assert await identity.authenticate("anything", "anything") is None


# ------------------------------------------------------------------ contact
async def test_adding_an_email_makes_the_account_findable(session):
    """Which is what lets a colleague add them to a book."""
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    await identity.set_contact(user.id, email="Emad@Example.COM")

    assert user.email == "emad@example.com"          # normalised
    found = await identity.find_by_identifier("emad@example.com")
    assert found is not None and found.id == user.id


async def test_a_phone_number_is_normalised_from_persian_digits(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    await identity.set_contact(user.id, phone="۰۹۱۲۱۲۳۴۵۶۷")
    assert user.phone == "09121234567"


async def test_an_address_someone_else_holds_is_refused_without_saying_whose(session):
    identity = IdentityService(session)
    first = await identity.create_user("اول", email="taken@example.com")
    second = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    with pytest.raises(ValidationError) as caught:
        await identity.set_contact(second.id, email="taken@example.com")

    # Confirming which addresses are registered would make this an account finder.
    assert "taken@example.com" not in str(caught.value)
    assert second.email is None
    assert first.email == "taken@example.com"


async def test_setting_the_address_you_already_have_is_not_a_conflict(session):
    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="me@example.com")

    await identity.set_contact(user.id, email="me@example.com")
    assert user.email == "me@example.com"


async def test_nonsense_contact_details_are_refused(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    for bad in ("not-an-email", "@example.com", "emad@localhost"):
        with pytest.raises(ValidationError):
            await identity.set_contact(user.id, email=bad)

    for bad in ("12345", "not digits", "1" * 20):
        with pytest.raises(ValidationError):
            await identity.set_contact(user.id, phone=bad)

    assert user.email is None and user.phone is None


async def test_setting_neither_is_a_mistake_worth_naming(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    with pytest.raises(ValidationError):
        await identity.set_contact(user.id)


# ----------------------------------------------------------------- password
async def test_a_first_password_needs_no_current_one(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await identity.set_contact(user.id, email="emad@example.com")

    await identity.set_password(user.id, "a-good-password")

    assert await identity.authenticate("emad@example.com", "a-good-password") is not None


async def test_changing_a_password_requires_the_current_one(session):
    """A stolen phone should not be able to take the web side quietly too."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد", email="emad@example.com",
                                      password="the-old-password")

    with pytest.raises(ValidationError):
        await identity.set_password(user.id, "a-new-password")

    with pytest.raises(ValidationError):
        await identity.set_password(user.id, "a-new-password",
                                    current_password="wrong")

    # The old one still works, so nothing was half-changed.
    assert await identity.authenticate("emad@example.com", "the-old-password") is not None

    await identity.set_password(user.id, "a-new-password",
                                current_password="the-old-password")
    assert await identity.authenticate("emad@example.com", "a-new-password") is not None
    assert await identity.authenticate("emad@example.com", "the-old-password") is None


async def test_a_short_password_is_refused_before_it_is_hashed(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    with pytest.raises(ValidationError):
        await identity.set_password(user.id, "1234")
    assert user.password_hash is None


async def test_the_password_is_never_stored_in_the_clear(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await identity.set_password(user.id, "a-good-password")

    assert "a-good-password" not in (user.password_hash or "")
    assert user.password_hash.startswith("$argon2")


# ------------------------------------------------------------------ profile
async def test_a_display_name_can_be_changed(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    await identity.update_profile(user.id, display_name="عماد حبیب‌نیا")
    assert user.display_name == "عماد حبیب‌نیا"

    with pytest.raises(ValidationError):
        await identity.update_profile(user.id, display_name="   ")


async def test_an_unknown_timezone_is_refused(session):
    """A bad zone sends the digest at the wrong hour and nobody connects the two."""
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    with pytest.raises(ValidationError):
        await identity.update_profile(user.id, timezone="Mars/Olympus")
    assert user.timezone == "Asia/Tehran"

    await identity.update_profile(user.id, timezone="Europe/Istanbul")
    assert user.timezone == "Europe/Istanbul"
