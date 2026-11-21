"""Bank accounts in the bot: see them, make one the default, move a transaction to one.

Driven through Conversation.handle(), the seam a Telegram update crosses. The bot never creates an
account (a card number is better typed in the panel); it reads, arranges and chooses.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from kasbbook.bot import screens
from kasbbook.modules.banks.service import BankService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from tests.test_bot_ux_fixes import datas, press, says, setup, tapped

pytestmark = pytest.mark.asyncio


async def two_accounts(session, user, book):
    banks = BankService(session)
    first = await banks.create(user.id, bank_name="ملی", holder_name="علی رضایی",
                               card_number="4111111111111111", book_ids=[book.id])
    second = await banks.create(user.id, bank_name="ملت", holder_name="علی رضایی",
                                display_name="حساب دوم", book_ids=[book.id])
    return first, second


async def test_the_book_menu_offers_the_accounts_and_they_are_listed_with_their_share(session):
    user, (book,), convo = await setup(session)
    first, second = await two_accounts(session, user, book)
    await LedgerService(session).record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 500)

    menu = await convo.handle(press(f"book:open:{book.id}"))
    assert f"ba:home:{book.id}" in datas(menu)

    home = await convo.handle(press(f"ba:home:{book.id}"))
    assert "ملی علی رضایی" in home.text and "حساب دوم" in home.text
    assert "1111" in home.text and "4111111111111111" not in home.text  # only the last four
    assert "500" in home.text and "پیش‌فرض" in home.text
    # The default is not offered again; the other one can be made so.
    assert datas(home).count(f"ba:df:{book.id}:{second.id.hex[:8]}") == 1
    assert f"ba:df:{book.id}:{first.id.hex[:8]}" not in datas(home)


async def test_an_empty_book_says_where_accounts_are_added(session):
    user, (book,), convo = await setup(session)
    home = await convo.handle(press(f"ba:home:{book.id}"))
    assert "پنل وب" in home.text


async def test_the_default_can_be_changed_from_the_bot(session):
    user, (book,), convo = await setup(session)
    first, second = await two_accounts(session, user, book)
    await convo.handle(press(f"ba:df:{book.id}:{second.id.hex[:8]}"))
    rows = await BankService(session).for_book(book.id, user.id)
    assert [row.bank.id for row in rows if row.link.is_default] == [second.id]


async def test_a_stale_account_button_is_refused_not_obeyed(session):
    user, (book,), convo = await setup(session)
    await two_accounts(session, user, book)
    reply = await convo.handle(press(f"ba:df:{book.id}:deadbeef"))
    assert "دیگر" in reply.text


async def test_a_quick_entry_says_which_account_it_went_through(session):
    user, (book,), convo = await setup(session)
    first, _ = await two_accounts(session, user, book)
    confirm = await convo.handle(says("قهوه ۳۰ هزار"))
    saved = await convo.handle(tapped(confirm, "qk:flow:expense"))
    assert "ملی علی رضایی" in saved.text
    row = (await LedgerService(session).transactions(book.id, user.id))[0]
    assert row.bank_account_id == first.id


async def test_a_transaction_can_be_moved_to_another_account_and_to_none(session):
    user, (book,), convo = await setup(session)
    first, second = await two_accounts(session, user, book)
    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قهوه", 40)
    assert tx.bank_account_id == first.id

    detail = await convo.handle(press(f"td:open:{tx.id}"))
    assert "حساب بانکی: ملی علی رضایی" in detail.text
    assert f"ba:pk:{tx.id}" in datas(detail)

    pick = await convo.handle(press(f"ba:pk:{tx.id}"))
    assert f"ba:st:{tx.id}:{second.id.hex[:8]}" in datas(pick)
    assert f"ba:st:{tx.id}:-" in datas(pick)

    done = await convo.handle(press(f"ba:st:{tx.id}:{second.id.hex[:8]}"))
    assert "حساب دوم" in done.text
    moved = await LedgerService(session).get_transaction(book.id, user.id, tx.id)
    assert moved.bank_account_id == second.id

    await convo.handle(press(f"ba:st:{tx.id}:-"))
    cleared = await LedgerService(session).get_transaction(book.id, user.id, tx.id)
    assert cleared.bank_account_id is None
    # The books agree after both moves.
    debit, credit = await LedgerService(session).trial_balance(book.id)
    assert debit == credit
    summary = await BankService(session).reconcile(user.id, first.id)
    assert summary.consistent and summary.from_journal == Decimal("0")


async def test_every_callback_the_bank_screens_emit_fits_the_provider_limit(session):
    user, (book,), convo = await setup(session)
    await two_accounts(session, user, book)
    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قهوه", 40)
    screens_seen = [
        await convo.handle(press(f"ba:home:{book.id}")),
        await convo.handle(press(f"ba:pk:{tx.id}:a")),
        await convo.handle(press(f"td:open:{tx.id}")),
    ]
    for reply in screens_seen:
        for data in datas(reply):
            assert len(data.encode()) <= 64, data
