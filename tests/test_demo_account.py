"""The demo account: a year of believable books to look at, gone when the visitor leaves."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from kasbbook.modules.books.models import Book
from kasbbook.modules.identity.models import User
from kasbbook.modules.ledger.models import Transaction
from kasbbook.modules.ledger.service import LedgerService
from tests.test_api_auth import bearer

pytestmark = pytest.mark.asyncio


async def test_the_demo_has_four_books_of_every_kind_and_plenty_of_rows(api, db):
    made = await api.post("/api/v1/auth/demo")
    assert made.status_code == 201, made.text
    tokens = made.json()

    books = (await api.get("/api/v1/books", headers=bearer(tokens))).json()

    assert sorted(b["type"] for b in books) == ["business", "organization", "personal", "team"]
    assert {b["name"] for b in books} >= {"حساب‌داری شخصی"}
    assert (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()["is_guest"] is True
    async for s in db.session():
        assert (await s.execute(select(func.count(Transaction.id)))).scalar() > 300
        # Every book's journal balances: it was made through the same services as a real one.
        for book in (await s.execute(select(Book))).scalars():
            debit, credit = await LedgerService(s).trial_balance(book.id)
            assert debit == credit


async def test_the_demo_uses_the_whole_panel(api, db):
    tokens = (await api.post("/api/v1/auth/demo")).json()
    books = {b["type"]: b for b in (await api.get("/api/v1/books", headers=bearer(tokens))).json()}

    async def get(path):
        r = await api.get(path, headers=bearer(tokens))
        assert r.status_code == 200, (path, r.text)
        return r.json()

    personal, team, org = books["personal"]["id"], books["team"]["id"], books["organization"]["id"]
    assert len(await get(f"/api/v1/books/{personal}/currencies")) > 3
    assert len(await get(f"/api/v1/books/{personal}/debts")) >= 3
    assert len(await get(f"/api/v1/books/{personal}/loans")) >= 2
    assert len((await get(f"/api/v1/books/{personal}/portfolio"))["holdings"]) >= 4
    assert len(await get(f"/api/v1/books/{personal}/capital/funds")) == 1
    assert len(await get(f"/api/v1/books/{personal}/portfolio/notes")) == 1
    assert len(await get(f"/api/v1/books/{personal}/recurring")) >= 2
    assert len(await get(f"/api/v1/books/{team}/members")) == 5
    assert len(await get(f"/api/v1/books/{org}/members")) == 7
    periods = await get(f"/api/v1/books/{team}/periods")
    assert len(periods) >= 6
    assert org and books["organization"]["calendar"] == "gregorian"


async def test_everyone_signs_in_to_the_same_demo_and_nothing_is_made_twice(api, db):
    first = (await api.post("/api/v1/auth/demo")).json()
    async for s in db.session():
        rows = (await s.execute(select(func.count(Transaction.id)))).scalar()
    second = (await api.post("/api/v1/auth/demo")).json()

    ids = []
    for tokens in (first, second):
        me = (await api.get("/api/v1/auth/me", headers=bearer(tokens))).json()
        assert me["is_demo"] is True and me["is_guest"] is True
        ids.append(me["id"])
    assert ids[0] == ids[1]
    async for s in db.session():
        assert (await s.execute(select(func.count(Transaction.id)))).scalar() == rows
        assert (await s.execute(select(func.count(Book.id)))).scalar() == 4


async def test_signing_out_of_the_demo_leaves_it_for_the_next_visitor(api, db):
    tokens = (await api.post("/api/v1/auth/demo")).json()

    out = await api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert out.status_code == 204
    again = (await api.post("/api/v1/auth/demo")).json()
    books = (await api.get("/api/v1/books", headers=bearer(again))).json()
    assert len(books) == 4
    everywhere = await api.post("/api/v1/auth/logout-everywhere", headers=bearer(again))
    assert everywhere.status_code == 204
    async for s in db.session():
        assert (await s.execute(select(func.count(Book.id)))).scalar() == 4


async def test_nobody_can_close_the_shared_demo(api, db):
    tokens = (await api.post("/api/v1/auth/demo")).json()

    refused = await api.delete("/api/v1/auth/me", headers=bearer(tokens))

    assert refused.status_code in (400, 422)
    async for s in db.session():
        assert (await s.execute(select(func.count(Book.id)))).scalar() == 4


async def test_an_old_demo_is_renewed_with_its_colleagues_replaced(api, db):
    from datetime import timedelta

    from kasbbook.shared.security import utcnow

    first = (await api.post("/api/v1/auth/demo")).json()
    old = (await api.get("/api/v1/auth/me", headers=bearer(first))).json()["id"]
    async for s in db.session():
        user = (await s.execute(select(User).where(User.id == uuid.UUID(old)))).scalar_one()
        user.created_at = utcnow() - timedelta(days=30)
        await s.commit()

    renewed = (await api.post("/api/v1/auth/demo")).json()

    new = (await api.get("/api/v1/auth/me", headers=bearer(renewed))).json()["id"]
    assert new != old
    async for s in db.session():
        assert (await s.execute(select(func.count(Book.id)))).scalar() == 4
        # 1 owner + 4 team colleagues + 6 organization colleagues, never the old set on top.
        assert (await s.execute(select(func.count(User.id)))).scalar() == 11
