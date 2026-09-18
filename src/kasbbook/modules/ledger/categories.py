"""Book-owned categories shared by recording, the API and the bot."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ..books.models import Book, Permission
from ..books.service import BookService
from ..budgets.models import Budget, BudgetKind
from ..recurring.models import RecurringRule
from ..treasury.models import TreasuryRule
from .models import Category, Flow, JournalEntry, Transaction


class CategoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.books = BookService(session)

    @staticmethod
    def name(value: str) -> str:
        value = value.strip()
        if not value or len(value) > 80:
            raise ValidationError("نام دسته‌بندی باید بین ۱ تا ۸۰ حرف باشد.")
        return value

    async def lock_book(self, book_id):
        # Recording and category mutations take the same lock so a concurrent
        # recording cannot race a rename/delete or create a duplicate category.
        await self.session.execute(select(Book.id).where(Book.id == book_id).with_for_update())

    async def list(self, book_id, actor_user_id):
        await self.books.require(book_id, actor_user_id, Permission.VIEW_TRANSACTIONS)
        return (await self.session.scalars(
            select(Category).where(Category.book_id == book_id).order_by(Category.name)
        )).all()

    async def get(self, book_id, actor_user_id, category_id):
        await self.books.require(book_id, actor_user_id, Permission.VIEW_TRANSACTIONS)
        row = await self.session.get(Category, category_id)
        if row is None or row.book_id != book_id:
            raise NotFound("این دسته‌بندی پیدا نشد.")
        return row

    async def _ensure(self, book_id, name):
        """Called only after recording permission and the book lock are held.

        Quick entries and debt/loan/recurring services still supply names; they
        register the same category rather than bypassing category management.
        """
        name = self.name(name)
        row = await self.session.scalar(select(Category).where(
            Category.book_id == book_id, Category.name == name
        ))
        if row is None:
            row = Category(book_id=book_id, name=name)
            self.session.add(row)
            await self.session.flush()
        return row

    async def require_create(self, book_id, actor_user_id):
        await self.books.require(book_id, actor_user_id, Permission.CREATE_CATEGORY)

    async def create(self, book_id, actor_user_id, name):
        await self.require_create(book_id, actor_user_id)
        await self.lock_book(book_id)
        name = self.name(name)
        if await self.session.scalar(select(Category.id).where(
            Category.book_id == book_id, Category.name == name
        )):
            raise ValidationError("این دسته‌بندی از قبل وجود دارد.")
        return await self._ensure(book_id, name)

    async def rename(self, book_id, actor_user_id, category_id, name):
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        await self.lock_book(book_id)
        row = await self.get(book_id, actor_user_id, category_id)
        name = self.name(name)
        if name == row.name:
            return row
        if await self.session.scalar(select(Category.id).where(
            Category.book_id == book_id, Category.name == name
        )):
            raise ValidationError("این نام دسته‌بندی از قبل وجود دارد.")
        # Planning uses category names too. Refuse a merge rather than silently
        # changing a budget's meaning or violating its unique target constraint.
        if await self.session.scalar(select(Budget.id).where(
            Budget.book_id == book_id, Budget.kind == BudgetKind.CATEGORY,
            Budget.target == name
        )):
            raise ValidationError("برای نام جدید بودجه وجود دارد؛ ابتدا بودجه را اصلاح کن.")
        old = row.name
        row.name = name
        await self.session.execute(update(Transaction).where(
            Transaction.book_id == book_id, Transaction.category_id == row.id
        ).values(category=name))
        await self.session.execute(update(JournalEntry).where(
            JournalEntry.book_id == book_id,
            JournalEntry.transaction_id.in_(select(Transaction.id).where(
                Transaction.book_id == book_id, Transaction.category_id == row.id,
                Transaction.flow == Flow.INCOME
            ))
        ).values(memo=f"income: {name}"))
        await self.session.execute(update(JournalEntry).where(
            JournalEntry.book_id == book_id,
            JournalEntry.transaction_id.in_(select(Transaction.id).where(
                Transaction.book_id == book_id, Transaction.category_id == row.id,
                Transaction.flow == Flow.EXPENSE
            ))
        ).values(memo=f"expense: {name}"))
        for model, column in ((Budget, Budget.target), (RecurringRule, RecurringRule.category),
                              (TreasuryRule, TreasuryRule.category)):
            conditions = [model.book_id == book_id, column == old]
            if model is Budget:
                conditions.append(Budget.kind == BudgetKind.CATEGORY)
            await self.session.execute(update(model).where(*conditions).values({column.key: name}))
        await self.session.flush()
        return row

    async def delete(self, book_id, actor_user_id, category_id):
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        await self.lock_book(book_id)
        row = await self.get(book_id, actor_user_id, category_id)
        if await self.session.scalar(select(Transaction.id).where(
            Transaction.book_id == book_id, Transaction.category_id == category_id
        ).limit(1)):
            raise ValidationError("این دسته‌بندی تراکنش دارد و قابل حذف نیست.")
        await self.session.delete(row)
        await self.session.flush()
