"""Money that changes shape: gold, loans that bought something kept, and a rotating fund.

The point of all of it is what it is not: none of it is income or an expense, and the books stay
balanced however it moves.
"""

from __future__ import annotations

import uuid

import pytest

from kasbbook.modules.ledger.service import LedgerService
from tests.test_api_auth import bearer, register

pytestmark = pytest.mark.asyncio


async def a_book(api, tokens):
    return (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]


async def figures(api, tokens, book):
    """Income, expense and the base wallet, read the way the panel reads them."""
    summary = (await api.get(f"/api/v1/books/{book['id']}/reports/summary", headers=bearer(tokens))).json()
    wallet = (await api.get(f"/api/v1/books/{book['id']}/wallet", headers=bearer(tokens))).json()
    cash = next((float(row["amount"]) for row in wallet if row["is_base"]), 0.0)
    return float(summary["income"]), float(summary["expense"]), cash


async def balanced(db, book):
    async for s in db.session():
        debit, credit = await LedgerService(s).trial_balance(uuid.UUID(book["id"]))
        return debit == credit


async def overview(api, tokens, book):
    return (await api.get(f"/api/v1/books/{book['id']}/capital/overview", headers=bearer(tokens))).json()


async def buy(api, tokens, book, **extra):
    body = {"name": "سکه", "kind": "gold", "cost": "50000000", "acquired_on": "2026-11-01", **extra}
    return await api.post(f"/api/v1/books/{book['id']}/capital/assets", headers=bearer(tokens), json=body)


# ------------------------------------------------------------------ assets
async def test_gold_bought_in_cash_is_an_asset_not_an_expense(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)

    made = await buy(api, tokens, book)

    assert made.status_code == 201, made.text
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense) == (0.0, 0.0)
    assert cash == -50_000_000
    assert float((await overview(api, tokens, book))["assets"]) == 50_000_000
    assert await balanced(db, book)


async def test_gold_bought_on_a_loan_moves_no_cash_and_owes_the_loan(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)

    made = await buy(api, tokens, book, installment_amount="5000000", installment_count=10,
                     loan_starts_on="2026-12-01")

    assert made.status_code == 201, made.text
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense, cash) == (0.0, 0.0, 0.0)
    result = await overview(api, tokens, book)
    assert float(result["assets"]) == 50_000_000 and float(result["liabilities"]) == 50_000_000
    assert float(result["net"]) == 0
    assert await balanced(db, book)


async def test_a_down_payment_leaves_the_wallet_and_the_rest_is_borrowed(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)

    await buy(api, tokens, book, down_payment="10000000", installment_amount="4000000",
              installment_count=10, loan_starts_on="2026-12-01")

    _, _, cash = await figures(api, tokens, book)
    assert cash == -10_000_000
    assert float((await overview(api, tokens, book))["liabilities"]) == 40_000_000
    assert await balanced(db, book)


async def test_installments_that_cannot_repay_the_loan_are_refused(api):
    tokens = await register(api)
    book = await a_book(api, tokens)

    refused = await buy(api, tokens, book, installment_amount="1000000", installment_count=10)

    assert refused.status_code == 422


async def test_a_capital_loan_installment_repays_debt_and_is_not_an_expense(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book, installment_amount="5000000", installment_count=10,
                      loan_starts_on="2026-12-01")).json()

    paid = await api.post(f"/api/v1/books/{book['id']}/loans/{made['loan_id']}/pay", headers=bearer(tokens))

    assert paid.status_code == 200, paid.text
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense) == (0.0, 0.0)
    assert cash == -5_000_000
    assert float((await overview(api, tokens, book))["liabilities"]) == 45_000_000
    assert paid.json()["kind"] == "capital" and paid.json()["paid_count"] == 1
    assert await balanced(db, book)


async def test_only_the_interest_in_an_installment_is_an_expense(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    # 50,000,000 borrowed, repaid as 10 x 5,500,000: 500,000 of every installment is interest.
    made = (await buy(api, tokens, book, installment_amount="5500000", installment_count=10,
                      loan_starts_on="2026-12-01")).json()

    await api.post(f"/api/v1/books/{book['id']}/loans/{made['loan_id']}/pay", headers=bearer(tokens))

    income, expense, cash = await figures(api, tokens, book)
    assert expense == 500_000 and income == 0.0
    assert cash == -5_500_000
    assert float((await overview(api, tokens, book))["liabilities"]) == 45_000_000
    assert await balanced(db, book)


async def test_paying_every_installment_clears_the_debt_exactly(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book, cost="10000000", installment_amount="3500000",
                      installment_count=3, loan_starts_on="2026-12-01")).json()

    for _ in range(3):
        paid = await api.post(f"/api/v1/books/{book['id']}/loans/{made['loan_id']}/pay", headers=bearer(tokens))
        assert paid.status_code == 200, paid.text

    assert float((await overview(api, tokens, book))["liabilities"]) == 0
    _, expense, _ = await figures(api, tokens, book)
    assert expense == 500_000  # 3 x 3,500,000 - 10,000,000
    assert await balanced(db, book)


async def test_a_capital_loan_cannot_be_deleted_on_its_own(api):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book, installment_amount="5000000", installment_count=10,
                      loan_starts_on="2026-12-01")).json()

    refused = await api.delete(f"/api/v1/books/{book['id']}/loans/{made['loan_id']}", headers=bearer(tokens))

    assert refused.status_code == 422


async def test_selling_returns_the_cost_and_only_the_gain_is_income(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book)).json()

    sold = await api.post(f"/api/v1/books/{book['id']}/capital/assets/{made['id']}/sell",
                          headers=bearer(tokens), json={"price": "62000000", "sold_on": "2026-12-01"})

    assert sold.status_code == 200, sold.text
    income, expense, cash = await figures(api, tokens, book)
    assert income == 12_000_000 and expense == 0.0
    assert cash == 12_000_000
    assert float((await overview(api, tokens, book))["assets"]) == 0
    assert await balanced(db, book)


async def test_selling_at_a_loss_is_an_expense_for_the_difference(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book)).json()

    await api.post(f"/api/v1/books/{book['id']}/capital/assets/{made['id']}/sell",
                   headers=bearer(tokens), json={"price": "45000000", "sold_on": "2026-12-01"})

    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense, cash) == (0.0, 5_000_000.0, -5_000_000.0)
    assert await balanced(db, book)


async def test_a_mistaken_purchase_can_be_taken_back_until_it_has_history(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book, installment_amount="5000000", installment_count=10,
                      loan_starts_on="2026-12-01")).json()

    gone = await api.delete(f"/api/v1/books/{book['id']}/capital/assets/{made['id']}", headers=bearer(tokens))

    assert gone.status_code == 204
    assert (await api.get(f"/api/v1/books/{book['id']}/capital/assets", headers=bearer(tokens))).json() == []
    assert (await api.get(f"/api/v1/books/{book['id']}/loans", headers=bearer(tokens))).json() == []
    result = await overview(api, tokens, book)
    assert float(result["assets"]) == 0 and float(result["liabilities"]) == 0
    assert await balanced(db, book)


async def test_a_purchase_whose_loan_has_been_paid_on_cannot_be_deleted(api):
    tokens = await register(api)
    book = await a_book(api, tokens)
    made = (await buy(api, tokens, book, installment_amount="5000000", installment_count=10,
                      loan_starts_on="2026-12-01")).json()
    await api.post(f"/api/v1/books/{book['id']}/loans/{made['loan_id']}/pay", headers=bearer(tokens))

    refused = await api.delete(f"/api/v1/books/{book['id']}/capital/assets/{made['id']}", headers=bearer(tokens))

    assert refused.status_code == 422


# ------------------------------------------------------------------- funds
async def make_fund(api, tokens, book, **extra):
    body = {"name": "صندوق خواندگی", "monthly_amount": "5000000", "months": 20,
            "payout_amount": "100000000", "starts_on": "2026-11-01", "turn_month": 10, **extra}
    made = await api.post(f"/api/v1/books/{book['id']}/capital/funds", headers=bearer(tokens), json=body)
    assert made.status_code == 201, made.text
    return made.json()


async def pay_in(api, tokens, book, fund, on="2026-11-05"):
    return await api.post(f"/api/v1/books/{book['id']}/capital/funds/{fund['id']}/contribute",
                          headers=bearer(tokens), json={"on": on})


async def test_paying_into_a_fund_is_a_claim_not_an_expense(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    fund = await make_fund(api, tokens, book)

    for _ in range(3):
        assert (await pay_in(api, tokens, book, fund)).status_code == 200

    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense, cash) == (0.0, 0.0, -15_000_000.0)
    result = await overview(api, tokens, book)
    assert float(result["fund_claims"]) == 15_000_000 and float(result["net"]) == 15_000_000
    assert await balanced(db, book)


async def test_the_turn_is_cash_in_that_is_not_income(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    fund = await make_fund(api, tokens, book)
    for _ in range(10):
        await pay_in(api, tokens, book, fund)

    got = await api.post(f"/api/v1/books/{book['id']}/capital/funds/{fund['id']}/receive",
                         headers=bearer(tokens), json={"on": "2026-11-20"})

    assert got.status_code == 200, got.text
    body = got.json()
    # 50,000,000 had been paid in; the other 50,000,000 is owed back through the remaining months.
    assert float(body["claim"]) == 0 and float(body["owed"]) == 50_000_000
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense) == (0.0, 0.0)
    assert cash == 50_000_000
    result = await overview(api, tokens, book)
    assert float(result["fund_claims"]) == 0 and float(result["liabilities"]) == 50_000_000
    assert await balanced(db, book)


async def test_after_the_turn_each_month_pays_the_debt_back_to_nothing(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    fund = await make_fund(api, tokens, book)
    for _ in range(10):
        await pay_in(api, tokens, book, fund)
    await api.post(f"/api/v1/books/{book['id']}/capital/funds/{fund['id']}/receive",
                   headers=bearer(tokens), json={"on": "2026-11-20"})

    for _ in range(10):
        assert (await pay_in(api, tokens, book, fund)).status_code == 200

    result = await overview(api, tokens, book)
    assert float(result["liabilities"]) == 0 and float(result["net"]) == 0
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense, cash) == (0.0, 0.0, 0.0)
    assert await balanced(db, book)
    assert (await pay_in(api, tokens, book, fund)).status_code == 422  # every month is paid


async def test_the_turn_can_only_be_taken_once(api):
    tokens = await register(api)
    book = await a_book(api, tokens)
    fund = await make_fund(api, tokens, book)
    url = f"/api/v1/books/{book['id']}/capital/funds/{fund['id']}/receive"
    await api.post(url, headers=bearer(tokens), json={"on": "2026-11-20"})

    assert (await api.post(url, headers=bearer(tokens), json={"on": "2026-11-21"})).status_code == 422


async def test_a_fund_with_history_cannot_be_deleted(api):
    tokens = await register(api)
    book = await a_book(api, tokens)
    fund = await make_fund(api, tokens, book)
    assert (await api.delete(f"/api/v1/books/{book['id']}/capital/funds/{fund['id']}",
                             headers=bearer(tokens))).status_code == 204
    other = await make_fund(api, tokens, book, name="دیگر")
    await pay_in(api, tokens, book, other)

    refused = await api.delete(f"/api/v1/books/{book['id']}/capital/funds/{other['id']}", headers=bearer(tokens))

    assert refused.status_code == 422


async def test_a_stranger_sees_none_of_it(api):
    owner = await register(api)
    book = await a_book(api, owner)
    await buy(api, owner, book)
    stranger = await register(api, email="sara@example.com")

    for path in ("overview", "assets", "funds"):
        response = await api.get(f"/api/v1/books/{book['id']}/capital/{path}", headers=bearer(stranger))
        assert response.status_code == 404


# ------------------------------------------- one table of what is held
async def make_loan(api, tokens, book, **extra):
    body = {"title": "وام خودرو", "installment_amount": "5000000", "installment_count": 10,
            "starts_on": "2026-12-01", **extra}
    return (await api.post(f"/api/v1/books/{book['id']}/loans",
                           headers=bearer(tokens), json=body)).json()


async def held(api, tokens, book):
    return (await api.get(f"/api/v1/books/{book['id']}/portfolio", headers=bearer(tokens))).json()


async def test_an_asset_with_an_instrument_is_listed_with_the_things_held(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)

    made = await buy(api, tokens, book, name="", instrument="gold18", quantity="2", cost="50000000")

    assert made.status_code == 201, made.text
    assert made.json()["instrument"] == "gold18"
    table = await held(api, tokens, book)
    row = next(r for r in table["holdings"] if r["kind"] == "asset")
    assert row["name"] == "طلای ۱۸ عیار" and row["unit"] == "گرم" and float(row["cost"]) == 50_000_000


async def test_a_house_or_a_car_is_listed_at_what_it_cost(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await buy(api, tokens, book, name="پراید", kind="other", cost="300000000")

    table = await held(api, tokens, book)

    row = next(r for r in table["holdings"] if r["name"] == "پراید")
    assert row["kind"] == "asset" and float(row["value"]) == 300_000_000 and row["price_source"] == "cost"
    assert float(table["total_value"]) == 300_000_000


async def test_a_purchase_can_be_tied_to_a_loan_already_made(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    loan = await make_loan(api, tokens, book)

    made = await buy(api, tokens, book, name="ماشین", loan_id=loan["id"], down_payment="10000000")

    assert made.status_code == 201, made.text
    assert made.json()["loan_id"] == loan["id"]
    income, expense, cash = await figures(api, tokens, book)
    assert (income, expense, cash) == (0.0, 0.0, -10_000_000)
    assert float((await overview(api, tokens, book))["liabilities"]) == 40_000_000
    loans = (await api.get(f"/api/v1/books/{book['id']}/loans", headers=bearer(tokens))).json()
    assert next(l for l in loans if l["id"] == loan["id"])["kind"] == "capital"
    assert await balanced(db, book)
    # Taking the purchase back gives the loan back as it was, not gone.
    gone = await api.delete(f"/api/v1/books/{book['id']}/capital/assets/{made.json()['id']}", headers=bearer(tokens))
    assert gone.status_code == 204
    loans = (await api.get(f"/api/v1/books/{book['id']}/loans", headers=bearer(tokens))).json()
    assert next(l for l in loans if l["id"] == loan["id"])["kind"] == "consumer"


async def test_a_loan_that_is_too_small_or_already_paid_on_cannot_be_tied(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    small = await make_loan(api, tokens, book, installment_amount="1000000", installment_count=2)

    refused = await buy(api, tokens, book, name="ماشین", loan_id=small["id"])

    assert refused.status_code == 422
    other = await make_loan(api, tokens, book, title="دیگر")
    await api.post(f"/api/v1/books/{book['id']}/loans/{other['id']}/pay", headers=bearer(tokens))
    paid = await buy(api, tokens, book, name="ماشین", loan_id=other["id"])
    assert paid.status_code == 422
