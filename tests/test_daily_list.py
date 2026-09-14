"""The daily list and the dated single entry, as the first generation had them.

What the old bot got right and the rewrite lost: one press to a day, the
business and the person split apart, and "new" at the top of the list rather
than three screens away. What is new: the list spans every book a person is
on — a team, a shop, a household — each keeping its own totals, with a filter
to narrow it to one.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.state import MemoryStateStore
from kasbbook.modules.books.models import BookType, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.models import Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger import service as ledger_service
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.reports.service import ReportService
from kasbbook.shared import jalali
from kasbbook.shared.errors import NotFound
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

TG = Provider.TELEGRAM
DAY = date(2026, 3, 19)          # 1404/12/28, the day in the screenshot
TOKEN = "20260319"
SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"


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


async def conversation(session):
    return Conversation(session, MemoryStateStore(), TG)


async def linked_user(session, name="عماد", external_id="555001"):
    identity = IdentityService(session)
    user = await identity.create_user(name)
    issued = await identity.start_link_from_web(user.id, TG)
    await identity.complete_link_from_messenger(issued.token, TG, external_id)
    return user


async def shop_day(session):
    """A shop's day with every kind of line on it, and the next day beside it."""
    user = await linked_user(session)
    shop = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    ledger = LedgerService(session)
    for flow, scope, category, amount in (
        (Flow.INCOME, Scope.WORK, "نت ملی", 1_000),
        (Flow.EXPENSE, Scope.WORK, "خرید جنس", 300),
        (Flow.INCOME, Scope.PERSONAL, "هدیه", 50),
        (Flow.EXPENSE, Scope.PERSONAL, "شارژ و اینترنت", 80),
        (Flow.EXPENSE, Scope.PERSONAL, "قسط", 20),
    ):
        await ledger.record(shop.id, user.id, flow, scope, category, amount, occurred_on=DAY)
    await ledger.record(shop.id, user.id, Flow.INCOME, Scope.WORK, "فردا", 999,
                        occurred_on=DAY + timedelta(days=1))
    return user, shop


def labels(reply):
    return [b.text for row in reply.buttons for b in row]


def rows(reply):
    return [[b.text for b in row] for row in reply.buttons]


# ================================================================ the rule
async def test_a_shops_day_splits_the_way_the_first_generation_did(session):
    user, shop = await shop_day(session)

    (sheet,) = await ReportService(session).day(user.id, DAY)
    totals = sheet.totals

    assert (totals.business_income, totals.business_expense, totals.business_net) == (
        Decimal("1000"), Decimal("300"), Decimal("700"))
    assert (totals.personal_income, totals.personal_expense, totals.installment) == (
        Decimal("50"), Decimal("80"), Decimal("20"))
    # 700 from the shop, plus 50 given, minus 80 spent — then the loan, last.
    assert totals.savings_operational == Decimal("670")
    assert totals.savings_final == Decimal("650")
    assert len(sheet.rows) == 5 and sheet.can_record

    debit, credit = await LedgerService(session).trial_balance(shop.id)
    assert debit == credit


async def test_the_day_covers_every_book_the_person_is_on_and_nobody_elses(session):
    user, shop = await shop_day(session)
    books = BookService(session)
    team = await books.create_book(user.id, "تیم الف", BookType.TEAM)

    other = await linked_user(session, name="سارا", external_id="555002")
    theirs = await books.create_book(other.id, "خانهٔ سارا", BookType.PERSONAL)
    await LedgerService(session).record(theirs.id, other.id, Flow.EXPENSE,
                                        Scope.PERSONAL, "خصوصی", 7, occurred_on=DAY)

    sheets = await ReportService(session).day(user.id, DAY)
    assert {sheet.book.id for sheet in sheets} == {shop.id, team.id}
    assert all(tx.category != "خصوصی" for sheet in sheets for tx in sheet.rows)

    with pytest.raises(NotFound):
        await ReportService(session).day(other.id, DAY, shop.id)


async def test_a_viewer_sees_the_day_but_is_not_offered_recording(session):
    user, shop = await shop_day(session)
    viewer = await linked_user(session, name="ناظر", external_id="555003")
    await BookService(session).add_member(user.id, shop.id, viewer.id, Role.VIEWER)

    (sheet,) = await ReportService(session).day(viewer.id, DAY)
    assert sheet.rows and not sheet.can_record


# =============================================================== the clock
async def test_today_is_the_persons_day_not_the_servers():
    """The server is on UTC; half past one in Tehran is still yesterday there."""
    late = datetime(2026, 3, 18, 22, 0, tzinfo=timezone.utc)

    assert jalali.today_in("Asia/Tehran", late) == DAY
    assert jalali.today_in("UTC", late) == date(2026, 3, 18)
    # A zone that does not exist falls back rather than making today unknown.
    assert jalali.today_in("Not/AZone", late) == DAY


async def test_an_undated_entry_is_stamped_with_the_books_day(session, monkeypatch):
    user = await linked_user(session)
    shop = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)

    asked = []

    def book_today(zone, now=None):
        asked.append(zone)
        return DAY

    monkeypatch.setattr(ledger_service.jalali, "today_in", book_today)
    tx = await LedgerService(session).record(shop.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 10)

    assert tx.occurred_on == DAY
    assert asked == ["Asia/Tehran"]


# ============================================================== single entry
async def test_recording_offers_a_single_entry_and_the_daily_list(session):
    await linked_user(session)
    convo = await conversation(session)

    reply = await convo.handle(press("tx:new"))
    data = [b.data for row in reply.buttons for b in row]
    assert "tx:one" in data
    assert any(d.startswith("dl:v:") for d in data)


async def test_a_single_entry_takes_a_typed_jalali_date(session):
    user = await linked_user(session)
    shop = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    reply = await convo.handle(press("tx:one"))  # one book, so straight to the date
    assert "تاریخ" in reply.text
    await convo.handle(press("tx:on:ask"))

    reply = await convo.handle(says("1404/12/28"))
    assert "1404/12/28" in reply.text
    # A shop has both kinds of money, so all four kinds are offered.
    assert len([d for d in (b.data for row in reply.buttons for b in row)
                if d.startswith("tx:type:")]) == 4

    await convo.handle(press("tx:type:pe"))
    await convo.handle(says("شارژ و اینترنت"))
    reply = await convo.handle(says("110000"))
    assert "ثبت شد" in reply.text

    (tx,) = await LedgerService(session).transactions(shop.id, user.id)
    assert (tx.occurred_on, tx.flow, tx.scope) == (DAY, Flow.EXPENSE, Scope.PERSONAL)
    assert tx.converted_amount == Decimal("110000")


async def test_a_date_that_is_not_one_is_asked_for_again(session):
    user = await linked_user(session)
    await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    convo = await conversation(session)

    await convo.handle(press("tx:one"))
    await convo.handle(press("tx:on:ask"))
    reply = await convo.handle(says("1404/13/40"))
    assert "تاریخ را بنویس" in reply.text


# ============================================================== daily list
async def test_the_daily_list_reads_like_the_old_one(session):
    await shop_day(session)
    convo = await conversation(session)

    reply = await convo.handle(press(f"dl:v:{TOKEN}:a:0"))

    for line in ("2026-03-19", "1404/12/28", "📊 گزارش روز",
                 "💰 درآمد کاری: 1,000", "🏢 هزینه کاری: 300", "➖ خالص کاری: 700",
                 "💵 درآمد شخصی: 50", "📄 قسط پرداختی: 20",
                 "👤 هزینه شخصی (بدون قسط): 80",
                 "💾 پس‌انداز عملیاتی: 670", "💾 پس‌انداز نهایی: 650"):
        assert line in reply.text, line

    assert ["نت ملی", "1,000"] in rows(reply)
    assert any("لیست درآمد کاری" in label for label in labels(reply))
    assert "فردا" not in labels(reply)  # tomorrow's line stays on tomorrow
    # One book: "new" offers its four kinds directly, as the old list did.
    assert len([b for row in reply.buttons for b in row
                if (b.data or "").startswith("dl:add:")]) == 4
    # One book: nothing to filter.
    assert not any("همه" in label for label in labels(reply))


async def test_previous_and_next_move_one_day_and_keep_the_filter(session):
    user, shop = await shop_day(session)
    convo = await conversation(session)

    reply = await convo.handle(press(f"dl:v:{TOKEN}:{shop.id}:0"))
    by_text = {b.text: b.data for row in reply.buttons for b in row}
    assert by_text["◀️ روز قبل"] == f"dl:v:20260318:{shop.id}:0"
    assert by_text["روز بعد ▶️"] == f"dl:v:20260320:{shop.id}:0"

    reply = await convo.handle(press(by_text["روز بعد ▶️"]))
    assert "1404/12/29" in reply.text
    assert "فردا" in labels(reply)


async def test_the_filter_shows_only_the_book_it_names(session):
    user, shop = await shop_day(session)
    team = await BookService(session).create_book(user.id, "تیم الف", BookType.TEAM)
    await LedgerService(session).record(team.id, user.id, Flow.EXPENSE, Scope.TEAM,
                                        "ناهار تیم", 40, occurred_on=DAY)
    convo = await conversation(session)

    everything = await convo.handle(press(f"dl:v:{TOKEN}:a:0"))
    assert "نت ملی" in labels(everything) and "ناهار تیم" in labels(everything)
    assert "✅ همه" in labels(everything)
    # Each book keeps its own summary; nothing is summed across them.
    assert "— 💼 مغازه —" in everything.text and "— 👥 تیم الف —" in everything.text

    only_team = await convo.handle(press(f"dl:v:{TOKEN}:{team.id}:0"))
    assert "ناهار تیم" in labels(only_team) and "نت ملی" not in labels(only_team)
    assert "🔎 فقط: 👥 تیم الف" in only_team.text
    assert "🏢 هزینه: 40" in only_team.text
    assert "پس‌انداز" not in only_team.text  # a team's money is not anyone's savings


async def test_adding_from_the_list_lands_on_that_day_and_comes_back(session):
    user, shop = await shop_day(session)
    convo = await conversation(session)

    await convo.handle(press(f"dl:add:{TOKEN}:{shop.id}:we:b"))
    await convo.handle(says("کرایه"))
    reply = await convo.handle(says("250"))

    assert "1404/12/28" in reply.text
    assert "🏢 هزینه کاری: 550" in reply.text
    assert ["کرایه", "250"] in rows(reply)

    added = [tx for tx in await LedgerService(session).transactions(shop.id, user.id, DAY, DAY)
             if tx.category == "کرایه"]
    assert len(added) == 1
    assert (added[0].flow, added[0].scope) == (Flow.EXPENSE, Scope.WORK)


async def test_adding_to_the_team_from_the_all_books_list(session):
    user, shop = await shop_day(session)
    team = await BookService(session).create_book(user.id, "تیم الف", BookType.TEAM)
    convo = await conversation(session)

    everything = await convo.handle(press(f"dl:v:{TOKEN}:a:0"))
    pick = next(b.data for row in everything.buttons for b in row
                if "تیم الف" in b.text and (b.data or "").startswith("dl:ab:"))

    kinds = await convo.handle(press(pick))
    offered = [b.data for row in kinds.buttons for b in row]
    assert f"dl:add:{TOKEN}:{team.id}:te:a" in offered
    # No personal or shop money in a team book.
    assert not any(":pe:" in d or ":we:" in d for d in offered)

    await convo.handle(press(f"dl:add:{TOKEN}:{team.id}:te:a"))
    await convo.handle(says("ناهار تیم"))
    reply = await convo.handle(says("40"))

    assert "— 👥 تیم الف —" in reply.text
    (tx,) = await LedgerService(session).transactions(team.id, user.id)
    assert (tx.scope, tx.occurred_on) == (Scope.TEAM, DAY)


async def test_deleting_from_the_list_comes_back_to_the_list(session):
    user, shop = await shop_day(session)
    convo = await conversation(session)
    ledger = LedgerService(session)
    target = next(tx for tx in await ledger.transactions(shop.id, user.id, DAY, DAY)
                  if tx.category == "خرید جنس")

    detail = await convo.handle(press(f"td:open:{target.id}:b"))
    back = next(b.data for row in detail.buttons for b in row if "بازگشت" in b.text)
    assert back == f"dl:v:{TOKEN}:{shop.id}:0"

    confirm = await convo.handle(press(f"td:del:{target.id}:b"))
    yes = next(b.data for row in confirm.buttons for b in row if "حذف کن" in b.text)
    assert yes == f"td:delok:{target.id}:b"

    reply = await convo.handle(press(yes))
    assert "1404/12/28" in reply.text and "🏢 هزینه کاری: 0" in reply.text

    debit, credit = await ledger.trial_balance(shop.id)
    assert debit == credit


async def test_a_typed_date_jumps_the_list(session):
    await shop_day(session)
    convo = await conversation(session)

    await convo.handle(press("dl:go:a"))
    reply = await convo.handle(says("2026-03-19"))
    assert "1404/12/28" in reply.text and "💾 پس‌انداز نهایی: 650" in reply.text


async def test_every_button_on_the_list_fits_a_callback_payload(session):
    """Telegram gives a callback sixty-four bytes and fails silently past them."""
    user, shop = await shop_day(session)
    team = await BookService(session).create_book(
        user.id, "تیمی با اسمی بسیار طولانی برای همین آزمون", BookType.TEAM)
    await LedgerService(session).record(team.id, user.id, Flow.EXPENSE, Scope.TEAM,
                                        "دسته" * 20, 1, occurred_on=DAY)
    convo = await conversation(session)

    replies = [
        await convo.handle(press(f"dl:v:{TOKEN}:a:0")),
        await convo.handle(press(f"dl:v:{TOKEN}:{team.id}:0")),
        await convo.handle(press(f"dl:ab:{TOKEN}:{team.id}")),
    ]
    (tx,) = await LedgerService(session).transactions(team.id, user.id)
    replies.append(await convo.handle(press(f"td:open:{tx.id}:b")))
    replies.append(await convo.handle(press(f"td:del:{tx.id}:b")))

    for reply in replies:
        for row in reply.buttons:
            for button in row:
                if button.data:
                    assert len(button.data.encode("utf-8")) <= 64, button.data


async def test_a_crafted_button_does_not_open_someone_elses_book(session):
    user, shop = await shop_day(session)
    sara = await linked_user(session, name="سارا", external_id="555002")
    await BookService(session).create_book(sara.id, "خانهٔ سارا", BookType.PERSONAL)
    stranger = await conversation(session)

    for data in (
        f"dl:v:{TOKEN}:{shop.id}:0",
        f"dl:ab:{TOKEN}:{shop.id}",
        f"dl:add:{TOKEN}:{shop.id}:wi:b",
        f"tx:book:{shop.id}",
    ):
        reply = await stranger.handle(press(data, external_id="555002"))
        assert "مغازه" not in reply.text, data
        assert "نت ملی" not in labels(reply), data


# ===================================================================== API
@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def test_the_day_over_http_is_the_bots_day(api):
    async def register(email):
        tokens = (await api.post("/api/v1/auth/register", json={
            "display_name": "عماد", "email": email, "password": "a-good-password",
        })).json()
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    owner = await register("owner@example.com")
    book = (await api.post("/api/v1/books", headers=owner,
                           json={"name": "مغازه", "type": "business"})).json()

    for flow, scope, category, amount in (
        ("income", "work", "نت ملی", "1000"),
        ("expense", "work", "خرید جنس", "300"),
        ("income", "personal", "هدیه", "50"),
        ("expense", "personal", "شارژ", "80"),
        ("expense", "personal", "قسط", "20"),
    ):
        response = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=owner, json={
            "flow": flow, "scope": scope, "category": category, "amount": amount,
            "occurred_on": DAY.isoformat(),
        })
        assert response.status_code in (200, 201), response.text

    response = await api.get(f"/api/v1/books/{book['id']}/reports/day",
                             params={"date": DAY.isoformat()}, headers=owner)
    assert response.status_code == 200, response.text
    body = response.json()

    assert isinstance(body["savings_final"], str)  # money is never a JSON number
    assert Decimal(body["business_net"]) == Decimal("700")
    assert Decimal(body["installment"]) == Decimal("20")
    assert Decimal(body["savings_operational"]) == Decimal("670")
    assert Decimal(body["savings_final"]) == Decimal("650")
    assert body["transaction_count"] == 5

    stranger = await register("stranger@example.com")
    response = await api.get(f"/api/v1/books/{book['id']}/reports/day",
                             params={"date": DAY.isoformat()}, headers=stranger)
    assert response.status_code == 404

    response = await api.get(f"/api/v1/books/{book['id']}/reports/day",
                             params={"date": "1404/12/28"}, headers=owner)
    assert response.status_code == 422
