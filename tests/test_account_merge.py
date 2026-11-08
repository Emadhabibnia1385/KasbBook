"""Signing up with a username, and folding two accounts into one when a messenger is connected.

A person registers on the web with a username and a password typed twice, then connects Telegram — which
already had an account of its own. Everything the Telegram account holds has to end up on the web one, and
nothing may be merged without the person at the messenger saying yes.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType, Membership, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider, User
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope, Transaction
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.errors import InvalidLinkToken, ValidationError

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM
DAY = date(2026, 8, 24)


# ------------------------------------------------------------- signing up
async def test_sign_up_with_a_username_and_the_password_twice(api):
    made = await api.post("/api/v1/auth/register", json={
        "username": "Emad_H", "password": "a-good-password", "password_confirm": "a-good-password"})
    assert made.status_code == 201, made.text
    me = (await api.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {made.json()['access_token']}"})).json()
    assert me["username"] == "emad_h" and me["display_name"] == "emad_h"

    again = await api.post("/api/v1/auth/login", json={"identifier": "emad_h", "password": "a-good-password"})
    assert again.status_code == 200


async def test_sign_up_refuses_two_different_passwords(api):
    mismatch = await api.post("/api/v1/auth/register", json={
        "username": "sara_k", "password": "a-good-password", "password_confirm": "another-password"})
    assert mismatch.status_code == 422


async def test_sign_up_refuses_a_taken_name(api):
    base = {"username": "sara_k", "password": "a-good-password"}
    assert (await api.post("/api/v1/auth/register", json=base)).status_code == 201
    taken = await api.post("/api/v1/auth/register", json={**base, "password": "a-good-password-2"})
    assert taken.status_code == 422


async def test_sign_up_refuses_a_name_that_cannot_be_a_username(api):
    short = await api.post("/api/v1/auth/register", json={"username": "ab", "password": "a-good-password"})
    assert short.status_code == 422


async def test_sign_up_with_nothing_to_name_the_account_is_refused(api):
    response = await api.post("/api/v1/auth/register", json={"password": "a-good-password"})
    assert response.status_code == 422


# ----------------------------------------------------------------- merging
async def web_account(session, username="web_user"):
    service = IdentityService(session)
    user = await service.create_user(username, password="a-good-password", with_book=True)
    await service.set_username(user.id, username)
    return service, user


async def telegram_account(session, external_id="777001"):
    service = IdentityService(session)
    user = await service.create_account_from_messenger(TG, external_id, display_name="سارا")
    return user


async def test_the_telegram_account_is_folded_into_the_web_one(session):
    service, web = await web_account(session)
    tg = await telegram_account(session)
    web_id, tg_id = web.id, tg.id
    books = BookService(session)
    shop = await books.create_book(tg.id, "مغازه", BookType.BUSINESS)
    shop_id = shop.id
    tx = await LedgerService(session).record(shop.id, tg.id, Flow.INCOME, Scope.WORK, "فروش", "1000", occurred_on=DAY)
    tx_id = tx.id
    await service.set_contact(tg.id, email="sara@example.com")

    issued = await service.start_link_from_web(web.id, TG)
    preview = await service.preview_merge(issued.token, TG, "777001")
    assert preview.keep_username == "web_user" and preview.absorb_books >= 1

    survivor = await service.complete_merge_from_messenger(issued.token, TG, "777001")
    assert survivor == web_id
    session.expire_all()

    # The Telegram account is gone and its identity now reaches the web account.
    assert await session.get(User, tg_id) is None
    identity = await service.find_identity(TG, "777001")
    assert identity.user_id == web_id

    # Its book is the web account's: owned by it, and the transaction is authored by it.
    owner = await session.scalar(select(Membership.role).where(Membership.book_id == shop_id, Membership.user_id == web_id))
    assert owner is Role.OWNER
    assert (await session.get(Transaction, tx_id)).actor_user_id == web_id

    # Contact details the web account lacked come across; its own login stays.
    merged = await session.get(User, web_id)
    assert merged.email == "sara@example.com" and merged.username == "web_user"
    assert merged.password_hash is not None


async def test_a_book_both_accounts_belong_to_keeps_the_stronger_role(session):
    service, web = await web_account(session)
    tg = await telegram_account(session)
    books = BookService(session)
    shared = await books.create_book(tg.id, "مشترک", BookType.TEAM)
    shared_id, web_id = shared.id, web.id
    await books.add_member(tg.id, shared.id, web.id, Role.VIEWER)

    issued = await service.start_link_from_web(web.id, TG)
    await service.complete_merge_from_messenger(issued.token, TG, "777001")
    session.expire_all()

    rows = (await session.execute(select(Membership).where(Membership.book_id == shared_id))).scalars().all()
    assert len(rows) == 1 and rows[0].user_id == web_id and rows[0].role is Role.OWNER


async def test_a_merge_needs_the_codes_to_match_and_will_not_run_twice(session):
    service, web = await web_account(session)
    await telegram_account(session)

    issued = await service.start_link_from_web(web.id, TG)
    with pytest.raises(InvalidLinkToken):
        await service.complete_merge_from_messenger(issued.token, Provider.BALE, "777001")  # wrong messenger
    with pytest.raises(InvalidLinkToken):
        await service.complete_merge_from_messenger(issued.token, TG, "nobody")  # no account there

    await service.complete_merge_from_messenger(issued.token, TG, "777001")
    with pytest.raises(InvalidLinkToken):
        await service.complete_merge_from_messenger(issued.token, TG, "777001")  # spent


async def test_a_guest_or_demo_account_is_never_merged(session):
    service, web = await web_account(session)
    guest = await service.create_guest()
    await service.start_link_from_web(web.id, TG)
    with pytest.raises(ValidationError):
        from kasbbook.modules.identity.merge import merge_accounts
        await merge_accounts(session, web.id, guest.id)


# --------------------------------------------------------------- the bot
def event(kind, external_id="777001", **kwargs) -> IncomingEvent:
    return IncomingEvent(
        kind=kind,
        identity=ChannelIdentity(provider=TG, external_id=external_id, username="sara", display_name="سارا"),
        chat_id=external_id, message_id="10", **kwargs,
    )


async def test_the_bot_asks_before_it_merges_and_does_nothing_on_no(session):
    service, web = await web_account(session)
    tg = await telegram_account(session)
    web_id, tg_id = web.id, tg.id
    convo = Conversation(session, MemoryStateStore(), TG)
    issued = await service.start_link_from_web(web.id, TG)

    asked = await convo.handle(event(EventKind.COMMAND, command="start", args=issued.token, text="/start"))
    assert "یکی" in asked.text and "web_user" in asked.text
    assert await session.get(User, tg_id) is not None            # nothing has moved yet

    declined = await convo.handle(event(EventKind.CALLBACK, callback_data="mg:no", callback_id="c"))
    assert "عوض نشد" in declined.text
    assert await session.get(User, tg_id) is not None

    # The code is still good: asking again and agreeing does the merge.
    await convo.handle(event(EventKind.COMMAND, command="start", args=issued.token, text="/start"))
    done = await convo.handle(event(EventKind.CALLBACK, callback_data="mg:yes", callback_id="c"))
    assert "یکی شد" in done.text
    session.expire_all()
    assert await session.get(User, tg_id) is None
    assert (await service.find_identity(TG, "777001")).user_id == web_id
