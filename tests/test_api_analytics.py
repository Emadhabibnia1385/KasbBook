"""The analytics series behind the web panel's charts.

A chart that is wrong looks exactly like one that is right, so what is asserted
here is the arithmetic a picture would hide: percentages against a zero, a
running total that stops at today, a weekday that starts on Saturday, and a
currency conversion that must not read as income. A stranger gets a 404 for
every one of them.
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from decimal import Decimal

from kasbbook.modules.reports.analytics import change
from kasbbook.shared import jalali
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
BASE = "/api/v1/books"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def signed_in(api, email):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": email, "password": "a-good-password"})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def new_book(api, headers):
    return (await api.post(BASE, headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]


async def add(api, headers, book, flow, amount, on, category=None, scope="work", **extra):
    response = await api.post(f"{BASE}/{book}/transactions", headers=headers, json={
        "flow": flow, "scope": scope, "amount": amount, "occurred_on": on.isoformat(),
        "category": category or ("فروش" if flow == "income" else "اجاره"), **extra})
    assert response.status_code == 201, response.text


def day(y, m, d):
    return jalali.from_parts(y, m, d)


def today():
    return jalali.today_in("Asia/Tehran")


async def test_a_shrinking_loss_is_an_improvement_not_a_further_fall():
    # -100 to -50 is a gain of 50; dividing by the signed old figure says -50.
    assert change(Decimal("-50"), Decimal("-100")).percent == Decimal("50.00")
    assert change(Decimal("5"), Decimal("0")).percent is None


# ------------------------------------------------------------- cashflow
async def test_cashflow_gives_each_month_a_rate_and_a_running_total(api):
    headers = await signed_in(api, "a@example.com")
    book = await new_book(api, headers)
    now = today()
    last = jalali.add_months(now, -1)
    await add(api, headers, book, "income", "500", last)
    await add(api, headers, book, "expense", "700", last)
    await add(api, headers, book, "income", "1000.50", now)
    await add(api, headers, book, "expense", "400", now)

    rows = (await api.get(f"{BASE}/{book}/analytics/cashflow?months=3", headers=headers)).json()

    assert len(rows) == 3
    empty, previous, current = rows
    # A month with nothing in it still appears, and has no rate rather than a zero one.
    assert (empty["income"], empty["savings_rate_percent"], empty["transaction_count"]) == ("0.0000", None, 0)
    # Spending more than was earned is a negative rate, not a clamped zero.
    assert (previous["net"], previous["savings_rate_percent"]) == ("-200.0000", "-40.00")
    assert (current["net"], current["savings_rate_percent"]) == ("600.5000", "60.02")
    assert [r["cumulative_net"] for r in rows] == ["0.0000", "-200.0000", "400.5000"]
    y, m, _ = jalali.to_parts(now)
    assert current["period"] == f"{y}-{m:02d}"


# -------------------------------------------------------------- weekday
async def test_weekday_starts_on_saturday_and_sums_each_day(api):
    headers = await signed_in(api, "b@example.com")
    book = await new_book(api, headers)
    saturday = day(1404, 5, 1)
    while saturday.weekday() != 5:  # Python's Monday is 0, so Saturday is 5
        saturday += dt.timedelta(days=1)
    friday = saturday + dt.timedelta(days=6)
    await add(api, headers, book, "expense", "100", saturday)
    await add(api, headers, book, "expense", "50.25", saturday)
    await add(api, headers, book, "income", "900", friday)

    rows = (await api.get(f"{BASE}/{book}/analytics/weekday?period=1404-05", headers=headers)).json()

    assert [r["label"] for r in rows] == ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
    assert (rows[0]["expense"], rows[0]["transaction_count"]) == ("150.2500", 2)
    assert (rows[6]["income"], rows[6]["transaction_count"]) == ("900.0000", 1)
    assert all(r["transaction_count"] == 0 for r in rows[1:6])


# ---------------------------------------------------------------- scope
async def test_scope_split_lists_every_scope_and_ignores_conversions(api):
    headers = await signed_in(api, "c@example.com")
    book = await new_book(api, headers)
    on = day(1404, 5, 10)
    await add(api, headers, book, "income", "1000", on, scope="work")
    await add(api, headers, book, "expense", "300", on, scope="personal")
    # Held as tether, then swapped for the base currency: a conversion earns
    # and spends nothing, so no scope's totals may move.
    await api.put(f"{BASE}/{book}/currencies/USDT", headers=headers, json={"enabled": True})
    await add(api, headers, book, "income", "10", on, scope="team", currency="USDT", conversion_rate="100")
    convert = await api.post(f"{BASE}/{book}/conversions", headers=headers, json={
        "from_currency": "USDT", "from_amount": "4", "to_currency": "IRT", "to_amount": "400",
        "occurred_on": on.isoformat()})
    assert convert.status_code == 201, convert.text

    rows = (await api.get(f"{BASE}/{book}/analytics/scope-split?period=1404-05", headers=headers)).json()

    assert [r["scope"] for r in rows] == ["work", "personal", "team"]
    by = {r["scope"]: r for r in rows}
    assert (by["work"]["income"], by["work"]["net"]) == ("1000.0000", "1000.0000")
    assert (by["personal"]["expense"], by["personal"]["net"]) == ("300.0000", "-300.0000")
    assert (by["team"]["income"], by["team"]["transaction_count"]) == ("1000.0000", 1)


# -------------------------------------------------- compare + categories
async def test_compare_measures_change_against_the_previous_month(api):
    headers = await signed_in(api, "d@example.com")
    book = await new_book(api, headers)
    await add(api, headers, book, "income", "1000", day(1404, 4, 5))
    await add(api, headers, book, "expense", "200", day(1404, 4, 6), category="اجاره")
    await add(api, headers, book, "expense", "100", day(1404, 4, 7), category="حقوق")
    await add(api, headers, book, "income", "1500", day(1404, 5, 5))
    await add(api, headers, book, "expense", "300", day(1404, 5, 6), category="اجاره")
    await add(api, headers, book, "expense", "50", day(1404, 5, 7), category="تبلیغات")

    body = (await api.get(f"{BASE}/{book}/analytics/compare?period=1404-05", headers=headers)).json()

    assert (body["period"], body["previous_period"]) == ("1404-05", "1404-04")
    assert body["income"] == {"absolute": "500.0000", "percent": "50.00"}
    assert body["expense"] == {"absolute": "50.0000", "percent": "16.67"}
    # 700 -> 1150 net: measured against the old figure.
    assert body["net"]["absolute"] == "450.0000" and body["net"]["percent"] == "64.29"
    cats = {c["category"]: c for c in body["expense_categories"]}
    assert cats["اجاره"]["percent"] == "50.00"
    # New this month: growth from nothing has no percentage, not infinity.
    assert (cats["تبلیغات"]["previous"], cats["تبلیغات"]["percent"]) == ("0.0000", None)
    # Gone this month: it is still listed, at minus a hundred.
    assert (cats["حقوق"]["current"], cats["حقوق"]["percent"]) == ("0.0000", "-100.00")


async def test_top_categories_carry_share_and_delta_and_respect_the_limit(api):
    headers = await signed_in(api, "e@example.com")
    book = await new_book(api, headers)
    await add(api, headers, book, "expense", "100", day(1404, 4, 6), category="اجاره")
    await add(api, headers, book, "expense", "600", day(1404, 5, 6), category="اجاره")
    await add(api, headers, book, "expense", "300", day(1404, 5, 7), category="حقوق")
    await add(api, headers, book, "expense", "100", day(1404, 5, 8), category="تبلیغات")

    rows = (await api.get(f"{BASE}/{book}/analytics/top-categories?period=1404-05&limit=2", headers=headers)).json()

    assert [r["category"] for r in rows] == ["اجاره", "حقوق"]
    # Shares are of the whole month (1000), not of the two rows shown.
    assert [r["share_percent"] for r in rows] == ["60.00", "30.00"]
    assert (rows[0]["previous"], rows[0]["absolute"], rows[0]["percent"]) == ("100.0000", "500.0000", "500.00")
    assert rows[1]["percent"] is None


# ----------------------------------------------------------- cumulative
async def test_cumulative_lines_are_aligned_by_day_number(api):
    headers = await signed_in(api, "f@example.com")
    book = await new_book(api, headers)
    await add(api, headers, book, "income", "100", day(1404, 4, 1))
    await add(api, headers, book, "expense", "30", day(1404, 4, 2))
    await add(api, headers, book, "income", "1000", day(1404, 5, 1))
    await add(api, headers, book, "expense", "400", day(1404, 5, 3))

    body = (await api.get(f"{BASE}/{book}/analytics/cumulative?period=1404-05", headers=headers)).json()

    days = body["days"]
    # Mordad has 31 days and Tir 31 as well: both lines are fully drawn.
    assert len(days) == 31
    assert (days[0]["net"], days[0]["previous_net"]) == ("1000.0000", "100.0000")
    assert (days[1]["net"], days[1]["previous_net"]) == ("1000.0000", "70.0000")
    assert (days[2]["income"], days[2]["expense"], days[2]["net"]) == ("1000.0000", "400.0000", "600.0000")
    assert days[30]["net"] == "600.0000" and days[30]["on"] == day(1404, 5, 31).isoformat()


async def test_cumulative_stops_at_today_instead_of_drawing_a_flat_line(api):
    headers = await signed_in(api, "g@example.com")
    book = await new_book(api, headers)
    now = today()
    await add(api, headers, book, "income", "100", now)

    body = (await api.get(f"{BASE}/{book}/analytics/cumulative", headers=headers)).json()

    _, _, d = jalali.to_parts(now)
    days = body["days"]
    assert days[d - 1]["net"] == "100.0000"
    # Days that have not happened carry nothing, so the line ends where the month has.
    assert all(p["net"] is None for p in days[d:] if p["on"] is not None)
    # Spans the longer of the two months so last month's line is never cut short.
    assert len(days) >= d


# ------------------------------------------------------------- overview
async def test_overview_kpis_for_a_finished_month(api):
    headers = await signed_in(api, "h@example.com")
    book = await new_book(api, headers)
    await add(api, headers, book, "income", "10000", day(1404, 5, 2))
    await add(api, headers, book, "expense", "3100", day(1404, 5, 3), category="اجاره", description="ودیعه")
    await add(api, headers, book, "expense", "1000", day(1404, 5, 4), category="حقوق")

    body = (await api.get(f"{BASE}/{book}/analytics/overview-kpis?period=1404-05", headers=headers)).json()

    assert body["currency"] == "IRT"
    assert (body["income"], body["expense"], body["net"]) == ("10000.0000", "4100.0000", "5900.0000")
    assert body["savings_rate_percent"] == "59.00"
    # The whole of a finished month is the denominator: 4100 over 31 days.
    assert (body["days_counted"], body["average_daily_expense"]) == (31, "132.2581")
    assert body["biggest_expense"] == {
        "category": "اجاره", "amount": "3100.0000", "on": day(1404, 5, 3).isoformat(), "description": "ودیعه"}
    assert body["base_balance"] == "5900.0000" and body["total_balance"] == "5900.0000"
    assert body["holds_other_currencies"] is False
    # 5900 / 132.2581 = 44.6 -> whole days that are fully covered.
    assert body["runway_days"] == 44


async def test_overview_has_no_runway_without_a_positive_balance_or_spending(api):
    headers = await signed_in(api, "i@example.com")
    book = await new_book(api, headers)
    empty = (await api.get(f"{BASE}/{book}/analytics/overview-kpis?period=1404-05", headers=headers)).json()
    assert (empty["runway_days"], empty["savings_rate_percent"], empty["biggest_expense"]) == (None, None, None)

    await add(api, headers, book, "expense", "500", day(1404, 5, 3))
    overspent = (await api.get(f"{BASE}/{book}/analytics/overview-kpis?period=1404-05", headers=headers)).json()
    assert overspent["base_balance"] == "-500.0000" and overspent["runway_days"] is None


async def test_total_balance_is_withheld_when_another_currency_has_no_price(api):
    headers = await signed_in(api, "j@example.com")
    book = await new_book(api, headers)
    on = day(1404, 5, 3)
    await api.put(f"{BASE}/{book}/currencies/USDT", headers=headers, json={"enabled": True})
    await add(api, headers, book, "income", "10", on, currency="USDT", conversion_rate="100")

    body = (await api.get(f"{BASE}/{book}/analytics/overview-kpis?period=1404-05", headers=headers)).json()

    # One unknown price makes the total a guess, so there is none.
    assert body["holds_other_currencies"] is True and body["total_balance"] is None
    assert body["base_balance"] == "0.0000"


# ------------------------------------------------------ budget vs actual
async def test_budget_vs_actual_reports_use_and_pace(api):
    headers = await signed_in(api, "k@example.com")
    book = await new_book(api, headers)
    await add(api, headers, book, "expense", "150", day(1404, 5, 3), category="اجاره")
    await api.put(f"{BASE}/{book}/budgets", headers=headers, json={"target": "اجاره", "amount": "100"})

    body = (await api.get(f"{BASE}/{book}/analytics/budget-vs-actual?period=1404-05", headers=headers)).json()

    assert body["elapsed_percent"] == 100  # a finished month
    (item,) = body["items"]
    assert (item["label"], item["limit"], item["spent"], item["remaining"]) == ("اجاره", "100.0000", "150.0000", "-50.0000")
    assert (item["percent_used"], item["over"]) == (150, True)


# -------------------------------------------------------------- refusals
async def test_a_period_that_makes_no_sense_is_refused(api):
    headers = await signed_in(api, "l@example.com")
    book = await new_book(api, headers)

    for path in ("weekday", "scope-split", "compare", "top-categories", "cumulative", "overview-kpis"):
        reply = await api.get(f"{BASE}/{book}/analytics/{path}?period=soon", headers=headers)
        assert reply.status_code == 422, path
    # Budgets are monthly; a year is not a month to measure a ceiling against.
    assert (await api.get(f"{BASE}/{book}/analytics/budget-vs-actual?period=1404", headers=headers)).status_code == 422
    assert (await api.get(f"{BASE}/{book}/analytics/top-categories?flow=sideways", headers=headers)).status_code == 422
    assert (await api.get(f"{BASE}/{book}/analytics/cashflow?months=99", headers=headers)).status_code == 422


async def test_the_documented_period_forms_all_work(api):
    headers = await signed_in(api, "m@example.com")
    book = await new_book(api, headers)

    for period in ("1404-05", "1404", "week"):
        reply = await api.get(f"{BASE}/{book}/analytics/compare?period={period}", headers=headers)
        assert reply.status_code == 200, period

    year = (await api.get(f"{BASE}/{book}/analytics/compare?period=1404", headers=headers)).json()
    assert (year["period"], year["previous_period"]) == ("1404", "1403")
    january = (await api.get(f"{BASE}/{book}/analytics/compare?period=1404-01", headers=headers)).json()
    assert january["previous_period"] == "1403-12"


# ------------------------------------------------------------- isolation
async def test_a_stranger_gets_not_found_from_every_endpoint(api):
    owner = await signed_in(api, "n@example.com")
    stranger = await signed_in(api, "o@example.com")
    book = await new_book(api, owner)

    for path in (
        "cashflow", "weekday", "scope-split", "compare", "top-categories",
        "cumulative", "overview-kpis", "budget-vs-actual",
    ):
        reply = await api.get(f"{BASE}/{book}/analytics/{path}", headers=stranger)
        assert reply.status_code == 404, path
        # And the owner is let in, so the 404 is the gate and not a broken route.
        assert (await api.get(f"{BASE}/{book}/analytics/{path}", headers=owner)).status_code == 200, path
