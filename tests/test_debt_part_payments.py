"""A debt can be paid in parts: what is left shrinks, and it closes when nothing is."""

from __future__ import annotations

import pytest

from tests.test_api_auth import bearer, register

pytestmark = pytest.mark.asyncio


async def a_debt(api, tokens, amount="1000", direction="owed_to_me"):
    book = (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]
    made = await api.post(f"/api/v1/books/{book['id']}/debts", headers=bearer(tokens),
                          json={"person": "سارا", "direction": direction, "amount": amount})
    assert made.status_code == 201, made.text
    return book, made.json()


async def pay(api, tokens, book, debt, **body):
    return await api.post(f"/api/v1/books/{book['id']}/debts/{debt['id']}/settle",
                          headers=bearer(tokens), json=body)


async def test_a_part_payment_leaves_the_rest_open(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens)

    paid = await pay(api, tokens, book, debt, amount="400")

    assert paid.status_code == 200
    body = paid.json()
    assert (body["is_settled"], body["paid"], body["remaining"]) == (False, "400.0000", "600.0000")


async def test_paying_the_rest_closes_it(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens)
    await pay(api, tokens, book, debt, amount="400")

    done = (await pay(api, tokens, book, debt, amount="600")).json()

    assert done["is_settled"] is True and done["remaining"] == "0.0000"


async def test_no_amount_pays_everything_that_is_left(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens)
    await pay(api, tokens, book, debt, amount="250")

    done = (await pay(api, tokens, book, debt)).json()

    assert done["is_settled"] is True and done["paid"] == "1000.0000"


async def test_more_than_is_left_is_refused(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens)
    await pay(api, tokens, book, debt, amount="900")

    over = await pay(api, tokens, book, debt, amount="200")

    assert over.status_code == 422


async def test_a_settled_debt_cannot_be_paid_again(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens)
    await pay(api, tokens, book, debt)

    again = await pay(api, tokens, book, debt, amount="1")

    assert again.status_code == 422


async def test_a_part_payment_records_only_what_was_paid(api):
    tokens = await register(api)
    book, debt = await a_debt(api, tokens, direction="i_owe")

    await pay(api, tokens, book, debt, amount="300", record_transaction=True)

    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert [(row["flow"], row["converted_amount"]) for row in listed["items"]] == [("expense", "300.0000")]


async def test_the_outstanding_total_counts_what_is_left(api, session):
    from kasbbook.modules.debts.service import DebtService
    import uuid

    tokens = await register(api)
    book, debt = await a_debt(api, tokens)
    await pay(api, tokens, book, debt, amount="400")
    me = (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()

    totals = await DebtService(session).totals(uuid.UUID(book["id"]), uuid.UUID(me["id"]))

    assert str(totals.owed_to_me) in ("600.0000", "600")
