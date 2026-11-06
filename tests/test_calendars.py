"""A book keeps its months by one of two calendars, and everything counted by month follows it."""

from __future__ import annotations

from datetime import date

import pytest

from kasbbook.shared import calendars
from kasbbook.shared.regions import region_for_zone
from tests.test_api_auth import api, bearer, register  # noqa: F401  (the api fixture)

pytestmark = pytest.mark.asyncio


# ----------------------------------------------------------- the calendars
def test_a_gregorian_month_is_the_usual_one():
    start, end = calendars.GREGORIAN.month_range(2026, 2)

    assert (start, end) == (date(2026, 2, 1), date(2026, 2, 28))
    assert calendars.GREGORIAN.month_range(2028, 2)[1] == date(2028, 2, 29)
    assert calendars.GREGORIAN.year_range(2026) == (date(2026, 1, 1), date(2026, 12, 31))


def test_a_jalali_month_is_unchanged():
    start, end = calendars.JALALI.month_range(1405, 1)

    assert start == date(2026, 3, 21) and end == date(2026, 4, 20)


def test_adding_a_month_clamps_onto_a_shorter_one():
    assert calendars.GREGORIAN.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert calendars.GREGORIAN.add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


def test_the_week_starts_where_the_calendar_starts_it():
    friday = date(2026, 11, 6)

    assert calendars.GREGORIAN.week_range(friday)[0] == date(2026, 11, 2)  # a Monday
    assert calendars.JALALI.week_range(friday)[0] == date(2026, 10, 31)  # a Saturday
    assert calendars.GREGORIAN.weekday_names[0] == "دوشنبه"
    assert calendars.JALALI.weekday_names[0] == "شنبه"


def test_an_unknown_calendar_name_is_the_jalali_one():
    assert calendars.named("lunar") is calendars.JALALI
    assert calendars.named(None) is calendars.JALALI
    assert calendars.named("Gregorian") is calendars.GREGORIAN


# ------------------------------------------------------------------ regions
def test_a_zone_suggests_money_and_calendar():
    tehran = region_for_zone("Asia/Tehran")
    kabul = region_for_zone("Asia/Kabul")
    berlin = region_for_zone("Europe/Berlin")
    new_york = region_for_zone("America/New_York")

    assert (tehran.currency, tehran.calendar) == ("IRT", "jalali")
    assert (kabul.currency, kabul.calendar) == ("AFN", "jalali")
    assert (berlin.currency, berlin.calendar) == ("EUR", "gregorian")
    assert (new_york.currency, new_york.calendar) == ("USD", "gregorian")


def test_a_zone_that_says_nothing_falls_back_on_the_default():
    assert region_for_zone(None).calendar == "jalali"
    assert region_for_zone("Mars/Olympus").currency == "IRT"


# ---------------------------------------------------------------- the books
async def make_book(api, tokens, **extra):
    body = {"name": "دفتر", "type": "business", **extra}
    return await api.post("/api/v1/books", headers=bearer(tokens), json=body)


async def record(api, tokens, book_id, on, amount="1000", flow="income"):
    made = await api.post(
        f"/api/v1/books/{book_id}/transactions", headers=bearer(tokens),
        json={"flow": flow, "scope": "work", "category": "فروش" if flow == "income" else "اجاره",
              "amount": amount, "occurred_on": on},
    )
    assert made.status_code == 201, made.text


async def test_a_book_is_made_on_the_calendar_asked_for(api):
    tokens = await register(api)

    made = await make_book(api, tokens, calendar="gregorian", currency="USD")

    assert made.status_code == 201
    assert made.json()["calendar"] == "gregorian" and made.json()["currency"] == "USD"
    assert (await make_book(api, tokens)).json()["calendar"] == "jalali"


async def test_an_unknown_calendar_is_refused(api):
    tokens = await register(api)

    assert (await make_book(api, tokens, calendar="lunar")).status_code == 422


async def test_the_calendar_can_be_changed_and_nothing_recorded_moves(api):
    tokens = await register(api)
    book = (await make_book(api, tokens)).json()
    await record(api, tokens, book["id"], "2026-02-10")

    changed = await api.put(f"/api/v1/books/{book['id']}/calendar", headers=bearer(tokens),
                            json={"calendar": "gregorian"})

    assert changed.status_code == 200 and changed.json()["calendar"] == "gregorian"
    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert [row["occurred_on"] for row in listed["items"]] == ["2026-02-10"]


async def test_a_gregorian_book_reports_by_gregorian_months(api):
    tokens = await register(api)
    book = (await make_book(api, tokens, calendar="gregorian")).json()
    for on in ("2026-02-01", "2026-02-28", "2026-03-01"):
        await record(api, tokens, book["id"], on)

    february = (await api.get(f"/api/v1/books/{book['id']}/reports/summary",
                              headers=bearer(tokens), params={"period": "2026-02"})).json()

    assert february["transaction_count"] == 2


async def test_a_jalali_book_still_reports_by_jalali_months(api):
    tokens = await register(api)
    book = (await make_book(api, tokens)).json()
    # 1404-12 (Esfand 1404) runs from 2026-02-20 to 2026-03-20.
    for on in ("2026-02-19", "2026-02-20", "2026-03-20", "2026-03-21"):
        await record(api, tokens, book["id"], on)

    esfand = (await api.get(f"/api/v1/books/{book['id']}/reports/summary",
                            headers=bearer(tokens), params={"period": "1404-12"})).json()

    assert esfand["transaction_count"] == 2


async def test_the_month_labels_follow_the_calendar(api):
    tokens = await register(api)
    book = (await make_book(api, tokens, calendar="gregorian")).json()

    rows = (await api.get(f"/api/v1/books/{book['id']}/reports/monthly",
                          headers=bearer(tokens), params={"months": 3})).json()

    from kasbbook.shared.calendars import GREGORIAN_MONTHS

    assert all(row["label"] in GREGORIAN_MONTHS for row in rows)


# ------------------------------------------------ the default book's region
async def test_the_default_book_follows_the_zone_while_it_is_untouched(api):
    tokens = await register(api)
    start = (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]
    assert (start["currency"], start["calendar"]) == ("IRT", "jalali")

    await api.patch("/api/v1/auth/me", headers=bearer(tokens), json={"timezone": "Europe/Berlin"})

    moved = (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]
    assert (moved["currency"], moved["calendar"]) == ("EUR", "gregorian")


async def test_a_default_book_with_history_keeps_its_money(api):
    tokens = await register(api)
    book = (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]
    await api.post(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens),
                   json={"flow": "income", "scope": "personal", "category": "حقوق",
                         "amount": "1000", "occurred_on": "2026-11-06"})

    await api.patch("/api/v1/auth/me", headers=bearer(tokens), json={"timezone": "Europe/Berlin"})

    kept = (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]
    assert (kept["currency"], kept["calendar"]) == ("IRT", "jalali")


async def test_a_new_account_in_another_zone_starts_with_its_region(session):
    from kasbbook.modules.books.service import BookService
    from kasbbook.modules.identity.service import IdentityService

    service = IdentityService(session)
    user = await service.create_user("سارا", email="sara@example.com")
    user.timezone = "Europe/Berlin"

    await service.ensure_default_book(user.id)

    books = await BookService(session).books_for_user(user.id)
    assert (books[0].base_currency, books[0].calendar) == ("EUR", "gregorian")
