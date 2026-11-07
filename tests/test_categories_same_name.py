"""One name may be both an income and an expense category; within one kind it stays unique."""

import pytest

from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.categories import CategoryService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.errors import ValidationError

pytestmark = pytest.mark.asyncio


async def setup(session):
    user = await IdentityService(session).create_user("Ali")
    book = await BookService(session).create_book(user.id, "Shop", BookType.BUSINESS)
    return user, book


async def test_the_same_name_is_an_income_and_an_expense(session):
    user, book = await setup(session)
    categories = CategoryService(session)

    income = await categories.create(book.id, user.id, "هدیه", "income")
    expense = await categories.create(book.id, user.id, "هدیه", "expense")

    assert income.id != expense.id
    assert (income.flow, expense.flow) == (Flow.INCOME, Flow.EXPENSE)
    with pytest.raises(ValidationError):
        await categories.create(book.id, user.id, "هدیه", "expense")


async def test_recording_either_way_uses_the_category_of_that_kind(session):
    user, book = await setup(session)
    ledger = LedgerService(session)

    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "هدیه", 100)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "هدیه", 40)
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "هدیه", 10)

    rows = [(c.name, c.flow) for c in await CategoryService(session).list(book.id, user.id)]
    assert sorted(rows, key=lambda r: r[1].value) == [("هدیه", Flow.EXPENSE), ("هدیه", Flow.INCOME)]


async def test_renaming_or_retyping_cannot_collide_inside_one_kind(session):
    user, book = await setup(session)
    categories = CategoryService(session)
    income = await categories.create(book.id, user.id, "فروش", "income")
    await categories.create(book.id, user.id, "فروش", "expense")
    other = await categories.create(book.id, user.id, "اجاره", "income")

    with pytest.raises(ValidationError):
        await categories.rename(book.id, user.id, other.id, "فروش")
    with pytest.raises(ValidationError):
        await categories.update(book.id, user.id, income.id, flow="expense")
    renamed = await categories.rename(book.id, user.id, income.id, "فروش کالا")
    assert renamed.name == "فروش کالا"
