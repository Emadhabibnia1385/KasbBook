"""The bot and the API obey the same rules, because the rules live in services.

Each section here is a rule that once lived in one client only, so the other
client either broke it or never had it. The tests pin the rule at the service
and then show that both doors reach it.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import SCOPE_FOR_BOOK, Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.settings import Settings
from tests.test_api_auth import SECRET, bearer, register

pytestmark = pytest.mark.asyncio

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "kasbbook"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


# ------------------------------------------------------------ default scope
@pytest.mark.parametrize("book_type, expected", [
    (BookType.PERSONAL, Scope.PERSONAL),
    (BookType.BUSINESS, Scope.WORK),
    (BookType.TEAM, Scope.TEAM),
    (BookType.ORGANIZATION, Scope.TEAM),
])
async def test_an_entry_with_no_scope_takes_its_books(session, book_type, expected):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "دفتر", book_type)

    tx = await LedgerService(session).record(book.id, user.id, Flow.INCOME, None,
                                             "فروش", "1000")

    assert tx.scope is expected
    assert await LedgerService(session).trial_balance(book.id) == (Decimal("1000"),
                                                                  Decimal("1000"))


async def test_a_named_scope_still_wins(session):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "تیم", BookType.TEAM)

    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE,
                                             Scope.PERSONAL, "قسط", "1000")

    assert tx.scope is Scope.PERSONAL


async def test_every_book_type_has_a_default_scope():
    assert set(SCOPE_FOR_BOOK) == set(BookType)


@pytest.mark.parametrize("book_type, expected", [
    ("personal", "personal"), ("business", "work"), ("team", "team"),
])
async def test_the_api_defaults_the_scope_as_the_bot_does(api, book_type, expected):
    headers = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "دفتر", "type": book_type})).json()

    made = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                          json={"flow": "income", "category": "فروش", "amount": "1000"})

    assert made.status_code == 201, made.text
    assert made.json()["scope"] == expected


async def test_a_stranger_recording_without_a_scope_still_gets_404(api):
    """The route used to look the book up to pick a scope; now the service does, behind its gate."""
    owner = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=owner,
                           json={"name": "دفتر", "type": "business"})).json()
    stranger = bearer(await register(api, email="other@example.com"))

    made = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=stranger,
                          json={"flow": "income", "category": "فروش", "amount": "1000"})

    assert made.status_code == 404


def _assignments_of(name: str):
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign) else [])
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                yield path.relative_to(SRC).as_posix()


async def test_the_scope_table_is_defined_once():
    """It was copied into the bot, the API router and the recurring loop."""
    assert list(_assignments_of("SCOPE_FOR_BOOK")) == ["modules/ledger/models.py"]
