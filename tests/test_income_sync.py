"""Income that follows a person from a team or business book into their own.

What is pinned, as the thing a person would notice if it broke: a late entry on a day already written
changes that day's amount instead of adding a second; a voided payment takes its income back; the same
event never writes twice; the target book refusing never stops the team's own entry; and nobody sees
anyone else's links.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from kasbbook.modules.income.models import IncomeEntry
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.payroll.models import FinancialPeriod, PeriodStatus
from tests.test_api_auth import bearer, register
from tests.test_bank_accounts import book_transfer, debt, make_bank, owner_with_two_books, record

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"
DAY = "2026-08-24"
NEXT = "2026-08-26"
START = "2026-08-01"


async def team(api):
    """An owner with a team book, and Sara, a member with a 40% share and a personal book of her own."""
    owner = bearer(await register(api, email="owner@example.com"))
    sara = bearer(await register(api, email="sara@example.com"))
    sara_id = (await api.get(f"{V1}/auth/me", headers=sara)).json()["id"]
    mine = (await api.get(f"{V1}/books", headers=sara)).json()[0]
    book = (await api.post(f"{V1}/books", headers=owner, json={"name": "کارگاه", "type": "team"})).json()
    await api.post(f"{V1}/books/{book['id']}/members", headers=owner,
                   json={"identifier": "sara@example.com", "role": "member"})
    share = await api.put(f"{V1}/books/{book['id']}/shares", headers=owner,
                          json={"user_id": sara_id, "basis": "percent", "value": "40",
                                "effective_from": "2026-01-01"})
    assert share.status_code == 200, share.text
    return owner, sara, book, mine


async def add(api, headers, book, flow, amount, day=DAY):
    reply = await api.post(f"{V1}/books/{book['id']}/transactions", headers=headers, json={
        "flow": flow, "category": "فروش" if flow == "income" else "اجاره", "amount": str(amount),
        "occurred_on": day})
    assert reply.status_code == 201, reply.text
    return reply.json()


async def link(api, headers, source, target, mode, **extra):
    return await api.post(f"{V1}/income-links", headers=headers, json={
        "source_book_id": source["id"], "target_book_id": target["id"], "mode": mode,
        "starts_on": START, **extra})


async def incomes(api, headers, book):
    """Each entry as (day, amount), an expense written as a negative amount."""
    page = (await api.get(f"{V1}/books/{book['id']}/transactions", headers=headers)).json()
    return sorted(
        (row["occurred_on"], Decimal(row["original_amount"]) * (1 if row["flow"] == "income" else -1))
        for row in page["items"]
    )


async def balanced(db, book_id):
    async for session in db.session():
        debit, credit = await LedgerService(session).trial_balance(uuid.UUID(str(book_id)))
        return debit == credit


# ------------------------------------------------------------------ running share
async def test_a_day_is_written_and_a_late_entry_changes_it_instead_of_adding_a_second(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    await add(api, owner, book, "expense", 20)

    made = await link(api, sara, book, mine, "daily")
    assert made.status_code == 201, made.text
    assert await incomes(api, sara, mine) == [(DAY, Decimal("32"))]  # 40% of 100 - 20

    # Someone records another income for that same day, after it was written.
    await add(api, owner, book, "income", 10)
    assert await incomes(api, sara, mine) == [(DAY, Decimal("36"))]  # 40% of 110 - 20, still one entry

    # A later day gets its own.
    await add(api, owner, book, "income", 50, day=NEXT)
    assert await incomes(api, sara, mine) == [(DAY, Decimal("36")), (NEXT, Decimal("20"))]
    assert await balanced(db, mine["id"]) and await balanced(db, book["id"])


async def test_correcting_or_deleting_the_source_follows(api, db):
    owner, sara, book, mine = await team(api)
    first = await add(api, owner, book, "income", 100)
    await link(api, sara, book, mine, "daily")
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]

    edited = await api.patch(f"{V1}/books/{book['id']}/transactions/{first['id']}", headers=owner,
                             json={"amount": "200"})
    assert edited.status_code == 200, edited.text
    assert await incomes(api, sara, mine) == [(DAY, Decimal("80"))]

    gone = await api.delete(f"{V1}/books/{book['id']}/transactions/{first['id']}", headers=owner)
    assert gone.status_code == 204
    assert await incomes(api, sara, mine) == []  # no income that day, so nothing to hold
    assert (await api.get(f"{V1}/income-links", headers=sara)).json()[0]["entries"] == 0


async def test_a_day_whose_costs_are_larger_is_a_share_of_the_loss_and_flips_back_with_income(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    await link(api, sara, book, mine, "daily")
    await add(api, owner, book, "expense", 500)
    # 40% of (100 - 500): her share of the loss, as an expense, not a day that vanishes.
    assert await incomes(api, sara, mine) == [(DAY, Decimal("-160"))]
    # Income arrives for that day later: the same entry becomes income again.
    await add(api, owner, book, "income", 1000)
    assert await incomes(api, sara, mine) == [(DAY, Decimal("240"))]  # 40% of (1100 - 500)
    assert await balanced(db, mine["id"])


async def test_costs_on_another_day_than_the_income_still_add_up_to_her_share_of_the_profit(api, db):
    owner, sara, book, mine = await team(api)
    for day in ("2026-08-21", "2026-08-22", "2026-08-23"):
        await add(api, owner, book, "income", 100, day=day)
    await add(api, owner, book, "expense", 90, day="2026-08-24")  # the costs fall on a day of their own
    made = (await link(api, sara, book, mine, "daily")).json()
    rows = await incomes(api, sara, mine)
    assert rows == [("2026-08-21", Decimal("40")), ("2026-08-22", Decimal("40")),
                    ("2026-08-23", Decimal("40")), ("2026-08-24", Decimal("-36"))]
    # Her share of the profit: 40% of (300 - 90), whatever days the costs and the income fell on.
    assert sum(amount for _, amount in rows) == Decimal("84")
    assert Decimal((await api.get(f"{V1}/income-links", headers=sara)).json()[0]["total"]) == 84
    assert made["entries"] == 4
    await add(api, owner, book, "expense", 10, day="2026-08-21")  # a later cost on an earlier day
    assert sum(amount for _, amount in await incomes(api, sara, mine)) == Decimal("80")


async def test_a_month_adds_up_the_same_way(api, db):
    # All inside one Jalali month (Mordad 1405 runs from 23 July to 22 August), the book's own calendar.
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 500, day="2026-08-03")
    await add(api, owner, book, "expense", 100, day="2026-08-10")
    await add(api, owner, book, "income", 100, day="2026-08-20")
    await link(api, sara, book, mine, "monthly")
    assert await incomes(api, sara, mine) == [("2026-08-20", Decimal("200"))]  # 40% of (600 - 100)
    await add(api, owner, book, "expense", 2000, day="2026-08-21")
    assert await incomes(api, sara, mine) == [("2026-08-21", Decimal("-600"))]  # 40% of (600 - 2100)


# ------------------------------------------------------------ a business that pays its owner
async def wallet_base(api, headers, book):
    rows = (await api.get(f"{V1}/books/{book['id']}/wallet", headers=headers)).json()
    return Decimal(next(row["amount"] for row in rows if row["is_base"]))


async def solo_business(api, db):
    owner = bearer(await register(api, email="solo2@example.com"))
    personal = (await api.get(f"{V1}/books", headers=owner)).json()[0]
    shop = (await api.post(f"{V1}/books", headers=owner, json={
        "name": "مغازه", "type": "business", "currency": personal["currency"]})).json()
    await api.post(f"{V1}/bank-accounts", headers=owner, json={
        "bank_name": "ملی", "holder_name": "علی", "book_ids": [shop["id"]]})
    return owner, personal, shop


async def test_the_net_taken_out_of_a_business_leaves_its_wallet_empty_and_follows_changes(api, db):
    owner, personal, shop = await solo_business(api, db)
    await add(api, owner, shop, "income", 500)
    await add(api, owner, shop, "expense", 100)
    assert await wallet_base(api, owner, shop) == 400

    made = (await link(api, owner, shop, personal, "monthly")).json()
    assert made["draws"] is True  # the default for a business
    assert await incomes(api, owner, personal) == [(DAY, Decimal("400"))]
    assert await wallet_base(api, owner, shop) == 0  # what the owner took is no longer held

    # More income in the same month: the income and the draw both follow, and the wallet is still empty.
    await add(api, owner, shop, "income", 250)
    assert await incomes(api, owner, personal) == [(DAY, Decimal("650"))]
    assert await wallet_base(api, owner, shop) == 0
    # The draw is not an expense: the business's own profit is untouched.
    page = (await api.get(f"{V1}/books/{shop['id']}/transactions", headers=owner)).json()
    assert Decimal(page["total_income"]) == 750 and Decimal(page["total_expense"]) == 100
    assert await balanced(db, shop["id"]) and await balanced(db, personal["id"])
    banks = (await api.get(f"{V1}/bank-accounts", headers=owner)).json()
    check = (await api.get(f"{V1}/bank-accounts/{banks[0]['id']}/reconciliation", headers=owner)).json()
    assert check["consistent"] is True


async def test_a_losing_month_puts_the_money_back_into_the_business(api, db):
    owner, personal, shop = await solo_business(api, db)
    await add(api, owner, shop, "income", 100)
    await link(api, owner, shop, personal, "monthly")
    await add(api, owner, shop, "expense", 400)  # costs beat the income: a share of the loss
    assert await incomes(api, owner, personal) == [(DAY, Decimal("-300"))]
    assert await wallet_base(api, owner, shop) == 0  # income 100 - costs 400 + 300 put back


async def test_a_link_without_draws_leaves_the_business_wallet_alone(api, db):
    owner, personal, shop = await solo_business(api, db)
    await add(api, owner, shop, "income", 500)
    made = (await link(api, owner, shop, personal, "monthly", draws=False)).json()
    assert made["draws"] is False
    assert await wallet_base(api, owner, shop) == 500
    # Turning it on takes the draw for what is already written; off puts it back.
    await api.patch(f"{V1}/income-links/{made['id']}", headers=owner, json={"draws": True})
    assert await wallet_base(api, owner, shop) == 0
    await api.patch(f"{V1}/income-links/{made['id']}", headers=owner, json={"draws": False})
    assert await wallet_base(api, owner, shop) == 500


async def test_taking_back_the_income_takes_back_the_draw(api, db):
    owner, personal, shop = await solo_business(api, db)
    await add(api, owner, shop, "income", 500)
    made = (await link(api, owner, shop, personal, "monthly")).json()
    assert await wallet_base(api, owner, shop) == 0
    await api.delete(f"{V1}/income-links/{made['id']}", headers=owner, params={"remove_income": "true"})
    assert await wallet_base(api, owner, shop) == 500
    assert await incomes(api, owner, personal) == []
    assert await balanced(db, shop["id"])


async def test_a_team_cannot_take_draws(api, db):
    owner, sara, book, mine = await team(api)
    reply = await link(api, sara, book, mine, "payment", draws=True)
    assert reply.status_code == 422


async def test_a_start_day_that_has_not_come_or_that_hides_the_transactions_is_explained(api, db):
    owner = bearer(await register(api, email="solo3@example.com"))
    personal = (await api.get(f"{V1}/books", headers=owner)).json()[0]
    shop = (await api.post(f"{V1}/books", headers=owner, json={
        "name": "مغازه", "type": "business", "currency": personal["currency"]})).json()
    await add(api, owner, shop, "income", 500, day="2026-08-10")
    await add(api, owner, shop, "income", 300, day="2026-08-12")

    future = (await api.post(f"{V1}/income-links", headers=owner, json={
        "source_book_id": shop["id"], "target_book_id": personal["id"], "mode": "monthly",
        "starts_on": "2030-01-01"})).json()
    assert future["entries"] == 0
    joined = " ".join(future["notes"])
    assert "هنوز نرسیده" in joined and "پیش از تاریخ شروع" in joined and "2" in joined.replace("۲", "2")

    # Moved back to before the transactions, nothing is left to explain.
    moved = await api.patch(f"{V1}/income-links/{future['id']}", headers=owner, json={"starts_on": "2026-08-01"})
    assert moved.json()["notes"] == [] and moved.json()["entries"] == 1


async def test_the_wallet_follows_money_moved_between_books_and_cash_lent(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    await record(api, headers, business, "income", 1000)
    await book_transfer(api, headers, business, personal, shop, mine, 300)
    assert await wallet_base(api, headers, business) == 700
    assert await wallet_base(api, headers, personal) == 300
    await debt(api, headers, business, amount="200", bank_account_id=shop["id"])
    assert await wallet_base(api, headers, business) == 500  # 200 lent out of the book



# ---------------------------------------------------- restored: rules, privacy, lifecycle
async def test_weekly_and_monthly_group_a_stretch_and_date_it_the_last_day_with_income(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100, day="2026-08-24")
    await add(api, owner, book, "income", 100, day="2026-08-25")
    await link(api, sara, book, mine, "monthly")
    rows = await incomes(api, sara, mine)
    assert rows == [("2026-08-25", Decimal("80"))]  # both days in one month, dated the later one


async def test_the_same_event_never_writes_twice(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    made = (await link(api, sara, book, mine, "daily")).json()
    for _ in range(3):
        assert (await api.post(f"{V1}/income-links/{made['id']}/resync", headers=sara)).status_code == 200
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]


async def test_nothing_before_the_start_day_is_written(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100, day="2026-07-01")
    await add(api, owner, book, "income", 100, day=DAY)
    await link(api, sara, book, mine, "daily")
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]


async def test_each_payment_is_written_and_a_void_takes_it_back(api, db):
    owner, sara, book, mine = await team(api)
    period, slip = await payroll_ready(api, owner, sara, book)
    await link(api, sara, book, mine, "payment")
    assert await incomes(api, sara, mine) == []

    first = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=owner,
                           json={"amount": "150", "paid_on": DAY})
    assert first.status_code == 201, first.text
    second = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=owner,
                            json={"amount": "50", "paid_on": NEXT})
    assert await incomes(api, sara, mine) == [(DAY, Decimal("150")), (NEXT, Decimal("50"))]

    payment_id = second.json()["payments"][-1]["id"]
    voided = await api.delete(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments/{payment_id}",
                              headers=owner)
    assert voided.status_code == 200, voided.text
    assert await incomes(api, sara, mine) == [(DAY, Decimal("150"))]
    assert await balanced(db, mine["id"])


async def test_a_closing_period_writes_the_net_pay_once_and_reopening_takes_it_back(api, db):
    owner, sara, book, mine = await team(api)
    period, slip = await payroll_ready(api, owner, sara, book)
    await link(api, sara, book, mine, "period")
    # Not settled yet: nothing.
    assert await incomes(api, sara, mine) == []

    for slip_row in (await api.get(f"{V1}/books/{book['id']}/periods/{period['id']}/payslips", headers=owner)).json():
        await api.post(f"{V1}/books/{book['id']}/payslips/{slip_row['id']}/payments", headers=owner,
                       json={"amount": slip_row["net_pay"], "paid_on": DAY})
    closed = await api.post(f"{V1}/books/{book['id']}/periods/{period['id']}/close", headers=owner)
    assert closed.status_code == 200, closed.text
    assert await incomes(api, sara, mine) == [("2026-08-31", Decimal("400"))]  # 40% of 1000, dated the period's end

    reopened = await api.post(f"{V1}/books/{book['id']}/periods/{period['id']}/reopen", headers=owner)
    assert reopened.status_code == 200, reopened.text
    assert await incomes(api, sara, mine) == []


async def test_a_business_book_writes_all_of_its_net_income_to_its_owner(api, db):
    owner = bearer(await register(api, email="solo@example.com"))
    personal = (await api.get(f"{V1}/books", headers=owner)).json()[0]
    shop = (await api.post(f"{V1}/books", headers=owner, json={
        "name": "مغازه", "type": "business", "currency": personal["currency"]})).json()
    await add(api, owner, shop, "income", 500)
    await add(api, owner, shop, "expense", 100)
    assert (await link(api, owner, shop, personal, "payment")).status_code == 422  # no payroll in a business
    made = await link(api, owner, shop, personal, "daily")
    assert made.status_code == 201, made.text
    assert await incomes(api, owner, personal) == [(DAY, Decimal("400"))]


async def test_a_closed_month_in_the_target_never_stops_the_teams_own_entry(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    made = (await link(api, sara, book, mine, "daily")).json()
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]

    # Sara's own month is closed after the fact.
    async for session in db.session():
        session.add(FinancialPeriod(book_id=uuid.UUID(mine["id"]), label="بسته",
                                    starts_on=datetime.date(2026, 8, 1), ends_on=datetime.date(2026, 8, 31),
                                    status=PeriodStatus.LOCKED))
        await session.commit()

    # The team records another income; its own entry must succeed.
    await add(api, owner, book, "income", 100)
    listed = (await api.get(f"{V1}/income-links", headers=sara)).json()[0]
    assert listed["problems"] == 1
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]  # not changed: the month is closed
    entries = (await api.get(f"{V1}/income-links/{made['id']}/entries", headers=sara)).json()
    assert entries[0]["problem"]


async def test_the_rules_of_a_link(api, db):
    owner, sara, book, mine = await team(api)
    # Not a personal source, not the same book, not someone else's book as the target.
    assert (await link(api, sara, mine, book, "daily")).status_code == 422
    assert (await link(api, sara, book, book, "daily")).status_code == 422
    assert (await link(api, sara, book, mine, "yearly")).status_code == 422
    owners_personal = (await api.get(f"{V1}/books", headers=owner)).json()[0]
    assert (await link(api, sara, book, owners_personal, "daily")).status_code in (403, 404, 422)
    assert (await link(api, sara, book, mine, "daily")).status_code == 201
    # One link per member per book, and no chains.
    assert (await link(api, sara, book, mine, "daily")).status_code == 422


async def test_a_share_that_is_not_a_percentage_cannot_use_a_running_mode(api, db):
    owner, sara, book, mine = await team(api)
    sara_id = (await api.get(f"{V1}/auth/me", headers=sara)).json()["id"]
    await api.put(f"{V1}/books/{book['id']}/shares", headers=owner,
                  json={"user_id": sara_id, "basis": "fixed", "value": "500",
                        "effective_from": "2026-01-01"})
    assert (await link(api, sara, book, mine, "daily")).status_code == 422
    assert (await link(api, sara, book, mine, "payment")).status_code == 201


async def test_links_are_private_to_their_owner(api, db):
    owner, sara, book, mine = await team(api)
    made = (await link(api, sara, book, mine, "daily")).json()
    assert (await api.get(f"{V1}/income-links", headers=owner)).json() == []
    for method, path, body in (
        ("get", f"{V1}/income-links/{made['id']}/entries", None),
        ("patch", f"{V1}/income-links/{made['id']}", {"is_active": False}),
        ("post", f"{V1}/income-links/{made['id']}/resync", None),
        ("delete", f"{V1}/income-links/{made['id']}", None),
    ):
        reply = await api.request(method.upper(), path, headers=owner, json=body)
        assert reply.status_code == 404, (method, path)


async def test_changing_the_mode_takes_back_the_old_income_and_writes_it_the_new_way(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100, day="2026-08-24")
    await add(api, owner, book, "income", 100, day="2026-08-25")
    made = (await link(api, sara, book, mine, "daily")).json()
    assert len(await incomes(api, sara, mine)) == 2
    moved = await api.patch(f"{V1}/income-links/{made['id']}", headers=sara, json={"mode": "monthly"})
    assert moved.status_code == 200, moved.text
    assert await incomes(api, sara, mine) == [("2026-08-25", Decimal("80"))]


async def test_a_switched_off_link_stops_and_resumes_catching_up(api, db):
    owner, sara, book, mine = await team(api)
    made = (await link(api, sara, book, mine, "daily")).json()
    await api.patch(f"{V1}/income-links/{made['id']}", headers=sara, json={"is_active": False})
    await add(api, owner, book, "income", 100)
    assert await incomes(api, sara, mine) == []
    await api.patch(f"{V1}/income-links/{made['id']}", headers=sara, json={"is_active": True})
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]


async def test_ending_a_link_keeps_the_income_unless_asked(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    made = (await link(api, sara, book, mine, "daily")).json()
    assert (await api.delete(f"{V1}/income-links/{made['id']}", headers=sara)).status_code == 204
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]  # stays, as an ordinary income

    again = (await link(api, sara, book, mine, "daily")).json()
    assert await incomes(api, sara, mine)  # the earlier one is now the link's again, or replaced: never lost
    await api.delete(f"{V1}/income-links/{again['id']}", headers=sara, params={"remove_income": "true"})
    async for session in db.session():
        assert (await session.scalars(select(IncomeEntry))).all() == []


async def test_a_member_who_left_keeps_what_was_written(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    await link(api, sara, book, mine, "daily")
    sara_id = (await api.get(f"{V1}/auth/me", headers=sara)).json()["id"]
    await api.delete(f"{V1}/books/{book['id']}/members/{sara_id}", headers=owner)
    await add(api, owner, book, "income", 100)
    assert await incomes(api, sara, mine) == [(DAY, Decimal("40"))]


async def test_the_income_is_filed_under_the_chosen_category_or_the_source_books_name(api, db):
    owner, sara, book, mine = await team(api)
    await add(api, owner, book, "income", 100)
    made = (await link(api, sara, book, mine, "daily")).json()
    assert made["category"] == book["name"]  # left out: the name of the book it comes from
    page = (await api.get(f"{V1}/books/{mine['id']}/transactions", headers=sara)).json()
    assert [row["category"] for row in page["items"]] == [book["name"]]

    await api.delete(f"{V1}/income-links/{made['id']}", headers=sara, params={"remove_income": "true"})
    chosen = (await link(api, sara, book, mine, "daily", category="حقوق")).json()
    assert chosen["category"] == "حقوق"
    page = (await api.get(f"{V1}/books/{mine['id']}/transactions", headers=sara)).json()
    assert [row["category"] for row in page["items"]] == ["حقوق"]



async def payroll_ready(api, owner, sara, book):
    sara_id = (await api.get(f"{V1}/auth/me", headers=sara)).json()["id"]
    owner_id = (await api.get(f"{V1}/auth/me", headers=owner)).json()["id"]
    await api.put(f"{V1}/books/{book['id']}/shares", headers=owner,
                  json={"user_id": owner_id, "basis": "percent", "value": "60",
                        "effective_from": "2026-01-01"})
    await add(api, owner, book, "income", 1000)
    period = (await api.post(f"{V1}/books/{book['id']}/periods", headers=owner, json={
        "label": "مرداد", "starts_on": "2026-08-01", "ends_on": "2026-08-31"})).json()
    slips = (await api.post(f"{V1}/books/{book['id']}/periods/{period['id']}/calculate", headers=owner)).json()
    slip = next(s for s in slips if s["user_id"] == sara_id)
    return period, slip
