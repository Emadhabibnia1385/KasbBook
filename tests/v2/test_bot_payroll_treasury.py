"""Payroll and treasury, driven the way a person drives them: buttons and text.

Both areas had complete services, complete models, and no way in. These tests
walk the whole thing from the book menu to money changing hands, because a
feature nobody can reach is indistinguishable from a feature that does not
work.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.payroll.models import ShareBasis, ShareRule
from kasbbook.modules.payroll.service import PayrollService
from kasbbook.modules.treasury.models import FundKind, RuleBasis
from kasbbook.modules.treasury.service import TreasuryService

pytestmark = pytest.mark.asyncio
TG = Provider.TELEGRAM

# Pinned. A payroll test that reads the real clock fails the day the Jalali
# month rolls over, for reasons nobody will connect to payroll.
DAY = date(2026, 8, 24)


def press(data, external_id="555001"):
    return IncomingEvent(
        kind=EventKind.CALLBACK,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", callback_data=data, callback_id="cb",
    )


def says(text, external_id="555001"):
    return IncomingEvent(
        kind=EventKind.MESSAGE,
        identity=ChannelIdentity(TG, external_id, "emad", "عماد"),
        chat_id=external_id, message_id="10", text=text,
    )


def labels(reply):
    return [b.text for row in reply.buttons for b in row]


async def team(session, income=Decimal("100000000"), expense=Decimal("20000000")):
    """A two-person team book with a month of trading behind it."""
    identity = IdentityService(session)
    owner = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(owner.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")

    colleague = await identity.create_user("سارا")

    books = BookService(session)
    book = await books.create_book(owner.id, "کارگاه", BookType.TEAM)
    await books.add_member(owner.id, book.id, colleague.id, Role.MEMBER)

    ledger = LedgerService(session)
    await ledger.record(book.id, owner.id, Flow.INCOME, Scope.TEAM, "فروش",
                        income, occurred_on=DAY)
    await ledger.record(book.id, owner.id, Flow.EXPENSE, Scope.TEAM, "اجاره",
                        expense, occurred_on=DAY)

    # Half each, so the arithmetic in the assertions is checkable by eye.
    for person in (owner, colleague):
        session.add(ShareRule(
            book_id=book.id, user_id=person.id, basis=ShareBasis.PERCENT,
            value=Decimal("50"), effective_from=date(2026, 1, 1),
        ))
    await session.flush()

    return owner, colleague, book, Conversation(session, MemoryStateStore(), TG)


# ------------------------------------------------------------- reachability
async def test_a_team_book_offers_payroll_from_its_menu(session):
    """The gap this whole file exists to close."""
    owner, _, book, convo = await team(session)
    reply = await convo.handle(press(f"book:open:{book.id}"))

    assert any("حقوق" in label for label in labels(reply))


async def test_a_personal_book_does_not(session):
    """Splitting profit between one person is not a feature, it is noise."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    book = await BookService(session).create_book(user.id, "خانه", BookType.PERSONAL)

    convo = Conversation(session, MemoryStateStore(), TG)
    reply = await convo.handle(press(f"book:open:{book.id}"))
    assert not any("حقوق" in label for label in labels(reply))


async def test_opening_payroll_on_a_personal_book_explains_rather_than_breaks(session):
    """The button is hidden, but the callback is still guessable."""
    identity = IdentityService(session)
    user = await identity.create_user("عماد")
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "555001")
    book = await BookService(session).create_book(user.id, "خانه", BookType.PERSONAL)

    convo = Conversation(session, MemoryStateStore(), TG)
    reply = await convo.handle(press(f"pr:list:{book.id}"))
    assert "تیمی" in reply.text


# ------------------------------------------------------------------ periods
async def test_a_period_can_be_opened_from_the_bot(session):
    owner, _, book, convo = await team(session)

    empty = await convo.handle(press(f"pr:list:{book.id}"))
    assert "دوره‌ای باز نشده" in empty.text

    opened = await convo.handle(press(f"pr:new:{book.id}"))
    periods = await PayrollService(session).periods(book.id, owner.id)
    assert len(periods) == 1
    assert "درآمد دوره" in opened.text


async def test_the_period_screen_shows_the_whole_arithmetic(session):
    """Someone about to be paid a share should see how the share was reached."""
    owner, _, book, convo = await team(session)
    reply = await convo.handle(press(f"pr:new:{book.id}"))

    assert "100,000,000" in reply.text   # income
    assert "20,000,000" in reply.text    # costs
    assert "80,000,000" in reply.text    # net, and distributable with no treasury


# ----------------------------------------------------------------- treasury
async def test_a_fund_and_a_rule_can_be_created_from_the_bot(session):
    owner, _, book, convo = await team(session)

    await convo.handle(press(f"tf:add:{book.id}"))
    await convo.handle(says("ذخیرهٔ اضطراری"))
    await convo.handle(press("tf:kind:emergency"))

    funds = await TreasuryService(session).funds(book.id, owner.id)
    assert len(funds) == 1
    assert funds[0].name == "ذخیرهٔ اضطراری"
    assert funds[0].kind is FundKind.EMERGENCY

    await convo.handle(press(f"tf:rule:{funds[0].id}"))
    await convo.handle(press("tf:basis:net_percent"))
    reply = await convo.handle(says("۱۰"))

    rules = await TreasuryService(session).rules(book.id, owner.id, funds[0].id)
    assert len(rules) == 1
    assert rules[0].value == Decimal("10")
    assert rules[0].basis is RuleBasis.NET_PERCENT
    assert "۱۰" in reply.text or "10" in reply.text


async def test_a_percentage_is_read_as_a_percentage_not_as_money(session):
    """"۱۰" is ten percent. The amount parser would read "۱۰م" as ten million."""
    owner, _, book, convo = await team(session)
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "مالیات", FundKind.TAX)

    await convo.handle(press(f"tf:rule:{fund.id}"))
    await convo.handle(press("tf:basis:gross_percent"))
    await convo.handle(says("۹"))

    rules = await treasury.rules(book.id, owner.id, fund.id)
    assert rules[0].value == Decimal("9")


async def test_a_percentage_over_a_hundred_is_refused(session):
    owner, _, book, convo = await team(session)
    treasury = TreasuryService(session)
    fund = await treasury.create_fund(book.id, owner.id, "مالیات", FundKind.TAX)

    await convo.handle(press(f"tf:rule:{fund.id}"))
    await convo.handle(press("tf:basis:gross_percent"))
    reply = await convo.handle(says("۱۵۰"))

    assert await treasury.rules(book.id, owner.id, fund.id) == []
    assert "۱۰۰" in reply.text or "100" in reply.text


async def test_the_treasury_cut_reduces_what_is_distributable(session):
    """The point of the whole feature, asserted as arithmetic."""
    owner, _, book, convo = await team(session)
    treasury = TreasuryService(session)

    fund = await treasury.create_fund(book.id, owner.id, "ذخیره", FundKind.EMERGENCY)
    await treasury.add_rule(
        book.id, owner.id, fund.id, RuleBasis.NET_PERCENT, Decimal("25"),
        effective_from=date(2026, 1, 1),
    )

    reply = await convo.handle(press(f"pr:new:{book.id}"))
    # Net is 80,000,000; a quarter goes to the fund, leaving 60,000,000.
    assert "20,000,000" in reply.text   # the treasury cut
    assert "60,000,000" in reply.text   # distributable


async def test_a_fund_that_has_taken_money_cannot_be_deleted(session):
    """Deleting it would leave a paid period pointing at nothing."""
    owner, _, book, convo = await team(session)
    treasury = TreasuryService(session)
    payroll = PayrollService(session)

    fund = await treasury.create_fund(book.id, owner.id, "ذخیره", FundKind.EMERGENCY)
    await treasury.add_rule(
        book.id, owner.id, fund.id, RuleBasis.NET_PERCENT, Decimal("10"),
        effective_from=date(2026, 1, 1),
    )
    period = await payroll.open_period(
        owner.id, book.id, "مرداد", date(2026, 7, 23), date(2026, 8, 22)
    )
    await payroll.calculate(owner.id, period.id)

    reply = await convo.handle(press(f"tf:del:{fund.id}"))
    assert "حذف نمی‌شود" in reply.text
    assert len(await treasury.funds(book.id, owner.id)) == 1


# ----------------------------------------------------------------- payslips
async def test_calculating_produces_a_payslip_per_member(session):
    owner, colleague, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))

    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    reply = await convo.handle(press(f"pr:calc:{period.id}"))
    assert "2 فیش" in reply.text

    slips = await PayrollService(session).payslips(owner.id, period.id)
    assert len(slips) == 2
    # Half of 80,000,000 each.
    assert all(slip.net_pay == Decimal("40000000") for slip in slips)


async def test_a_payslip_shows_where_its_number_came_from(session):
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = await PayrollService(session).payslips(owner.id, period.id)
    reply = await convo.handle(press(f"pr:slip:{slips[0].id}"))

    assert "80,000,000" in reply.text    # what was distributable
    assert "40,000,000" in reply.text    # this person's share
    assert "درصدی" in reply.text          # the basis it was worked out on


async def test_paying_in_full_settles_the_slip(session):
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = await PayrollService(session).payslips(owner.id, period.id)
    reply = await convo.handle(press(f"pr:payall:{slips[0].id}"))

    assert "کامل پرداخت شده" in reply.text


async def test_paying_in_instalments_tracks_what_is_left(session):
    """The normal case here: a share paid across several transfers."""
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = await PayrollService(session).payslips(owner.id, period.id)
    await convo.handle(press(f"pr:pay:{slips[0].id}"))
    reply = await convo.handle(says("۱۵م"))

    assert "15,000,000" in reply.text
    assert "25,000,000" in reply.text     # 40m owed, 15m paid
    assert "کامل پرداخت شده" not in reply.text


async def test_an_unreadable_payment_amount_asks_again(session):
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = await PayrollService(session).payslips(owner.id, period.id)
    await convo.handle(press(f"pr:pay:{slips[0].id}"))
    reply = await convo.handle(says("یه چیزی"))

    assert "چقدر" in reply.text
    assert slips[0].payments == []


# -------------------------------------------------------------- adjustments
async def test_a_bonus_can_be_added_from_the_bot(session):
    owner, colleague, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]

    await convo.handle(press(f"pr:adj:{period.id}"))
    await convo.handle(press(f"pr:adjadd:{period.id}"))
    await convo.handle(press(f"pr:adjwho:{colleague.id}"))
    await convo.handle(says("۲م"))
    reply = await convo.handle(says("پاداش پروژه"))

    adjustments = await PayrollService(session).adjustments(owner.id, period.id)
    assert len(adjustments) == 1
    assert adjustments[0].value == Decimal("2000000")
    assert adjustments[0].reason == "پاداش پروژه"
    assert "پاداش پروژه" in reply.text


async def test_a_deduction_is_a_negative_number_not_a_second_question(session):
    """One signed field, so a sign and a direction can never disagree."""
    owner, colleague, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]

    await convo.handle(press(f"pr:adjadd:{period.id}"))
    await convo.handle(press(f"pr:adjwho:{colleague.id}"))
    await convo.handle(says("-۵۰۰ک"))
    await convo.handle(press("pr:adjnoreason"))

    adjustments = await PayrollService(session).adjustments(owner.id, period.id)
    assert adjustments[0].value == Decimal("-500000")
    assert adjustments[0].kind.value == "penalty"


async def test_an_adjustment_lands_on_the_next_calculation(session):
    owner, colleague, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]
    payroll = PayrollService(session)

    await convo.handle(press(f"pr:adjadd:{period.id}"))
    await convo.handle(press(f"pr:adjwho:{colleague.id}"))
    await convo.handle(says("۲م"))
    await convo.handle(press("pr:adjnoreason"))
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = {s.user_id: s for s in await payroll.payslips(owner.id, period.id)}
    assert slips[colleague.id].net_pay == Decimal("42000000")
    assert slips[owner.id].net_pay == Decimal("40000000")


async def test_recalculating_replaces_the_slips_rather_than_doubling_them(session):
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))
    period = (await PayrollService(session).periods(book.id, owner.id))[0]

    await convo.handle(press(f"pr:calc:{period.id}"))
    await convo.handle(press(f"pr:calc:{period.id}"))

    slips = await PayrollService(session).payslips(owner.id, period.id)
    assert len(slips) == 2


# --------------------------------------------------------------- isolation
async def test_a_stranger_cannot_open_another_teams_payroll(session):
    owner, _, book, convo = await team(session)
    await convo.handle(press(f"pr:new:{book.id}"))

    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")

    other = Conversation(session, MemoryStateStore(), TG)
    reply = await other.handle(press(f"pr:list:{book.id}", external_id="999"))

    assert "کارگاه" not in reply.text


async def test_a_stranger_cannot_create_a_fund_in_another_teams_book(session):
    owner, _, book, convo = await team(session)

    identity = IdentityService(session)
    stranger = await identity.create_user("غریبه")
    issued = await identity.start_link_from_web(stranger.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, "999")

    other = Conversation(session, MemoryStateStore(), TG)
    await other.handle(press(f"tf:add:{book.id}", external_id="999"))
    await other.handle(says("صندوق غریبه", external_id="999"))
    await other.handle(press("tf:kind:main", external_id="999"))

    assert await TreasuryService(session).funds(book.id, owner.id) == []
