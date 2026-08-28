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
    NotFound,
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


# ======================================================= closing an account
#
# The hard case in a bookkeeping system: a person may leave, and the ledger
# must stay provable. Four foreign keys are RESTRICT — books.owner_user_id,
# transactions.actor_user_id, adjustments.recorded_by and
# recurring_rules.created_by_user_id — and each one is the database saying a
# financial record must not lose its author.

async def solo_book_with_money(session, user):
    from kasbbook.modules.books.models import BookType
    from kasbbook.modules.books.service import BookService
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService

    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    await LedgerService(session).record(
        book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 250_000
    )
    return book


async def test_an_account_that_owes_nothing_to_anyone_is_removed_outright(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await solo_book_with_money(session, user)

    removed = await identity.delete_account(user.id)

    assert removed is True
    with pytest.raises(NotFound):
        await identity.get_user(user.id)


async def test_the_books_go_with_it_and_so_does_the_journal(session):
    from sqlalchemy import func, select

    from kasbbook.modules.books.models import Book
    from kasbbook.modules.ledger.models import JournalLine, Transaction

    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await solo_book_with_money(session, user)

    async def count(model):
        return (await session.execute(select(func.count(model.id)))).scalar()

    assert await count(Transaction) == 1
    assert await count(JournalLine) == 2

    await identity.delete_account(user.id)

    assert await count(Book) == 0
    assert await count(Transaction) == 0
    assert await count(JournalLine) == 0


async def test_a_shared_book_stops_the_whole_thing_and_names_it(session):
    """A book other people are using is not one person's to throw away."""
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService

    identity = IdentityService(session)
    owner = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    colleague = await identity.create_user("سارا")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, colleague.id, Role.MEMBER)

    with pytest.raises(ValidationError) as caught:
        await identity.delete_account(owner.id)

    assert "کارگاه" in str(caught.value)
    # Nothing was half-done: the account and the book are both still there.
    assert await identity.get_user(owner.id) is not None
    assert len(await books.books_for_user(colleague.id)) == 1


async def test_after_handing_the_book_over_the_account_can_close(session):
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService

    identity = IdentityService(session)
    owner = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    colleague = await identity.create_user("سارا")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, colleague.id, Role.MEMBER)
    await books.transfer_ownership(owner.id, book.id, colleague.id)

    await identity.delete_account(owner.id)

    # The book survives, with its new owner.
    assert len(await books.books_for_user(colleague.id)) == 1


async def test_someone_who_recorded_in_anothers_book_is_anonymised_not_erased(session):
    """The ledger keeps its author; the person keeps nothing."""
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService

    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    leaver = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await identity.set_contact(leaver.id, email="leaving@example.com")
    await identity.set_password(leaver.id, "a-good-password")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, leaver.id, Role.MEMBER)
    transaction = await LedgerService(session).record(
        book.id, leaver.id, Flow.EXPENSE, Scope.TEAM, "خرید", 500
    )

    removed = await identity.delete_account(leaver.id)

    assert removed is False
    survivor = await identity.get_user(leaver.id)
    assert survivor.display_name == "حساب حذف‌شده"
    assert survivor.email is None and survivor.phone is None
    assert survivor.password_hash is None
    assert survivor.is_active is False

    # The transaction is intact and still names an author.
    assert transaction.actor_user_id == leaver.id
    assert len(await books.books_for_user(owner.id)) == 1


async def test_a_closed_account_cannot_be_signed_in_to(session):
    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    leaver = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await identity.set_contact(leaver.id, email="leaving@example.com")
    await identity.set_password(leaver.id, "a-good-password")

    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService
    from kasbbook.modules.ledger.models import Flow, Scope
    from kasbbook.modules.ledger.service import LedgerService

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, leaver.id, Role.MEMBER)
    await LedgerService(session).record(
        book.id, leaver.id, Flow.EXPENSE, Scope.TEAM, "خرید", 500
    )

    await identity.delete_account(leaver.id)

    assert await identity.authenticate("leaving@example.com", "a-good-password") is None


async def test_the_messenger_is_freed_and_can_start_again(session):
    """Somebody who closes an account and comes back is a new person, cleanly."""
    identity = IdentityService(session)
    first = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await identity.delete_account(first.id)

    assert await identity.user_for_identity(Provider.TELEGRAM, "555001") is None

    second = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    assert second.id != first.id


async def test_closing_ends_membership_of_other_peoples_books(session):
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService

    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    leaver = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, leaver.id, Role.MEMBER)

    await identity.delete_account(leaver.id)

    assert await books.membership(book.id, leaver.id) is None


# ------------------------------------------------------------------ preview
async def test_the_preview_says_what_would_go_and_what_blocks_it(session):
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService

    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    colleague = await identity.create_user("سارا")

    books = BookService(session)
    await books.create_book(user.id, "مغازه", BookType.BUSINESS)
    shared = await books.create_book(user.id, "کارگاه", BookType.TEAM)
    await books.add_member(user.id, shared.id, colleague.id, Role.MEMBER)

    preview = await identity.deletion_preview(user.id)

    assert preview.books_to_delete == ["مغازه"]
    assert preview.books_to_hand_over == ["کارگاه"]
    assert preview.blocked is True


async def test_the_preview_of_a_clean_account_blocks_nothing(session):
    identity = IdentityService(session)
    user = await identity.create_account_from_messenger(Provider.TELEGRAM, "555001")
    await solo_book_with_money(session, user)

    preview = await identity.deletion_preview(user.id)

    assert preview.books_to_delete == ["مغازه"]
    assert preview.books_to_hand_over == []
    assert preview.blocked is False


# -------------------------------------------------------------- book deletion
async def test_a_book_with_other_members_cannot_be_deleted(session):
    from kasbbook.modules.books.models import BookType, Role
    from kasbbook.modules.books.service import BookService

    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    colleague = await identity.create_user("سارا")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, colleague.id, Role.MEMBER)

    with pytest.raises(ValidationError):
        await books.delete_book(owner.id, book.id)


async def test_only_the_owner_may_delete_a_book(session):
    from kasbbook.modules.books.models import BookType
    from kasbbook.modules.books.service import BookService
    from kasbbook.shared.errors import PermissionDenied

    identity = IdentityService(session)
    owner = await identity.create_user("مالک")
    stranger = await identity.create_user("غریبه")

    books = BookService(session)
    book = await books.create_book(owner.id, "مغازه", BookType.BUSINESS)

    with pytest.raises(PermissionDenied):
        await books.delete_book(stranger.id, book.id)
