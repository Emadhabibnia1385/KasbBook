"""A repeating transaction that asks first: due dates wait in a queue until someone says yes or no."""

from __future__ import annotations

from datetime import date

import pytest

from kasbbook.modules.recurring.service import RecurringService
from tests.test_api_auth import api, bearer, register  # noqa: F401  (the api fixture)

pytestmark = pytest.mark.asyncio


async def a_book(api, tokens):
    return (await api.get("/api/v1/books", headers=bearer(tokens))).json()[0]


async def make_rule(api, tokens, book, **extra):
    body = {"flow": "expense", "category": "اجاره", "amount": "5000", "period": "monthly",
            "starts_on": "2026-10-05", **extra}
    made = await api.post(f"/api/v1/books/{book['id']}/recurring", headers=bearer(tokens), json=body)
    assert made.status_code == 201, made.text
    return made.json()


async def run_due(db, until):
    async for s in db.session():
        run = await RecurringService(s).run_due(until)
        await s.commit()
        return run


async def test_a_rule_asks_first_by_default(api):
    tokens = await register(api)
    book = await a_book(api, tokens)

    rule = await make_rule(api, tokens, book)

    assert rule["mode"] == "ask"


async def test_a_due_date_waits_instead_of_being_recorded(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book)

    run = await run_due(db, date(2026, 10, 6))

    assert len(run.pending) == 1 and run.booked == []
    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json()
    assert [(row["category"], row["due_on"], row["amount"]) for row in waiting] == [
        ("اجاره", "2026-10-05", "5000.0000")]
    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert listed["items"] == []


async def test_running_again_does_not_queue_the_same_date_twice(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book)

    await run_due(db, date(2026, 10, 6))
    await run_due(db, date(2026, 10, 6))

    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json()
    assert len(waiting) == 1


async def test_confirming_records_it_on_its_own_day(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book)
    await run_due(db, date(2026, 10, 6))
    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json()

    done = await api.post(
        f"/api/v1/books/{book['id']}/recurring/occurrences/{waiting[0]['id']}/confirm",
        headers=bearer(tokens), json={})

    assert done.status_code == 204
    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert [(row["category"], row["occurred_on"], row["converted_amount"]) for row in listed["items"]] == [
        ("اجاره", "2026-10-05", "5000.0000")]
    assert (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json() == []


async def test_the_amount_can_change_on_the_way_without_changing_the_rule(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    rule = await make_rule(api, tokens, book)
    await run_due(db, date(2026, 10, 6))
    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json()

    await api.post(f"/api/v1/books/{book['id']}/recurring/occurrences/{waiting[0]['id']}/confirm",
                   headers=bearer(tokens), json={"amount": "5750"})

    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert listed["items"][0]["converted_amount"] == "5750.0000"
    rules = (await api.get(f"/api/v1/books/{book['id']}/recurring", headers=bearer(tokens))).json()
    assert [r["amount"] for r in rules if r["id"] == rule["id"]] == ["5000.0000"]


async def test_skipping_records_nothing_and_it_cannot_be_answered_twice(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book)
    await run_due(db, date(2026, 10, 6))
    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(tokens))).json()
    base = f"/api/v1/books/{book['id']}/recurring/occurrences/{waiting[0]['id']}"

    skipped = await api.post(f"{base}/skip", headers=bearer(tokens))
    again = await api.post(f"{base}/confirm", headers=bearer(tokens), json={})

    assert skipped.status_code == 204 and again.status_code == 422
    listed = (await api.get(f"/api/v1/books/{book['id']}/transactions", headers=bearer(tokens))).json()
    assert listed["items"] == []


async def test_an_auto_rule_still_records_on_its_own(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book, mode="auto")

    run = await run_due(db, date(2026, 10, 6))

    assert len(run.booked) == 1 and run.pending == []


async def test_the_first_date_recorded_by_hand_starts_the_schedule_after_it(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)

    rule = await make_rule(api, tokens, book, first_booked=True)

    assert rule["next_run_on"] > "2026-10-05"
    run = await run_due(db, date(2026, 10, 6))
    assert run.pending == []


async def test_the_mode_can_be_changed_later(api):
    tokens = await register(api)
    book = await a_book(api, tokens)
    rule = await make_rule(api, tokens, book)

    changed = await api.patch(f"/api/v1/books/{book['id']}/recurring/{rule['id']}",
                              headers=bearer(tokens), json={"mode": "auto", "amount": "6000"})

    assert changed.status_code == 200
    assert changed.json()["mode"] == "auto" and changed.json()["amount"] == "6000.0000"
    assert (await api.patch(f"/api/v1/books/{book['id']}/recurring/{rule['id']}",
                            headers=bearer(tokens), json={"mode": "sometimes"})).status_code == 422


async def test_someone_outside_the_book_cannot_see_or_answer(api, db):
    owner = await register(api)
    book = await a_book(api, owner)
    await make_rule(api, owner, book)
    await run_due(db, date(2026, 10, 6))
    waiting = (await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(owner))).json()
    stranger = await register(api, email="sara@example.com")

    peek = await api.get(f"/api/v1/books/{book['id']}/recurring/pending", headers=bearer(stranger))
    answer = await api.post(
        f"/api/v1/books/{book['id']}/recurring/occurrences/{waiting[0]['id']}/confirm",
        headers=bearer(stranger), json={})

    assert peek.status_code == 404 and answer.status_code == 404


async def test_every_book_s_waiting_dates_come_in_one_list(api, db):
    tokens = await register(api)
    book = await a_book(api, tokens)
    await make_rule(api, tokens, book)
    await run_due(db, date(2026, 10, 6))

    everywhere = (await api.get("/api/v1/recurring/pending", headers=bearer(tokens))).json()

    assert [(row["book_name"], row["category"]) for row in everywhere] == [(book["name"], "اجاره")]
