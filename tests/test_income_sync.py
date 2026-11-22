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
