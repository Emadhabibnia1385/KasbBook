"""The demo account: a year of believable books to look at, gone when the visitor leaves."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from kasbbook.modules.books.models import Book, Membership
from kasbbook.modules.identity.models import User
from kasbbook.modules.ledger.models import Transaction
from kasbbook.modules.ledger.service import LedgerService
from tests.test_api_auth import api, bearer  # noqa: F401  (the api fixture)

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


async def test_signing_out_removes_the_demo_with_its_colleagues(api, db):
    tokens = (await api.post("/api/v1/auth/demo")).json()

    out = await api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert out.status_code == 204
    async for s in db.session():
        assert (await s.execute(select(func.count(Book.id)))).scalar() == 0
        assert (await s.execute(select(func.count(Transaction.id)))).scalar() == 0
        assert (await s.execute(select(func.count(User.id)))).scalar() == 0
        assert (await s.execute(select(func.count(Membership.id)))).scalar() == 0


async def test_demo_creation_is_limited(api):
    for _ in range(4):
        assert (await api.post("/api/v1/auth/demo")).status_code == 201

    assert (await api.post("/api/v1/auth/demo")).status_code == 429
