"""Book-owned categories shared by recording, the API and the bot."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.security import utcnow
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
            raise ValidationError("نام دسته باید بین 1 تا 80 حرف باشد.")
        return value

    async def lock_book(self, book_id):
        # Recording and category mutations take the same lock so a concurrent
        # recording cannot race a rename/delete or create a duplicate category.
        await self.session.execute(select(Book.id).where(Book.id == book_id).with_for_update())

    async def list(self, book_id, actor_user_id, flow=None):
        await self.books.require(book_id, actor_user_id, Permission.VIEW_TRANSACTIONS)
        query = select(Category).where(Category.book_id == book_id)
        if flow is not None:
            query = query.where(Category.flow == self.direction(flow))
        return (await self.session.scalars(
            query.order_by(Category.name)
        )).all()

    @staticmethod
    def direction(value):
        try:
            return Flow(value)
        except (ValueError, TypeError):
            raise ValidationError("نوع دسته باید درآمد یا هزینه باشد.") from None

    async def get(self, book_id, actor_user_id, category_id):
        await self.books.require(book_id, actor_user_id, Permission.VIEW_TRANSACTIONS)
        row = await self.session.scalar(select(Category).where(
            Category.id == category_id, Category.book_id == book_id
        ).execution_options(populate_existing=True))
        if row is None:
            raise NotFound("این دسته پیدا نشد.")
        return row

    async def _ensure(self, book_id, name, flow):
        """Called only after recording permission and the book lock are held.

        Quick entries and debt/loan/recurring services still supply names; they
        register the same category rather than bypassing category management.
        """
        name = self.name(name)
        flow = self.direction(flow)
        row = await self.session.scalar(select(Category).where(
            Category.book_id == book_id, Category.name == name
        ).execution_options(populate_existing=True))
        if row is None:
            row = Category(book_id=book_id, name=name, flow=flow)
            self.session.add(row)
            await self.session.flush()
        elif row.flow is not None and row.flow is not flow:
            raise ValidationError("نوع این دسته با تراکنش یکسان نیست؛ دستهٔ مناسب را انتخاب کن.")
        return row

    async def require_create(self, book_id, actor_user_id):
        await self.books.require(book_id, actor_user_id, Permission.CREATE_CATEGORY)

    async def create(self, book_id, actor_user_id, name, flow):
        await self.require_create(book_id, actor_user_id)
        await self.lock_book(book_id)
        name = self.name(name)
        if await self.session.scalar(select(Category.id).where(
            Category.book_id == book_id, Category.name == name
        )):
            raise ValidationError("این دسته از قبل وجود دارد.")
        return await self._ensure(book_id, name, flow)

    async def update(self, book_id, actor_user_id, category_id, *, name=None, flow=None):
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        if name is None and flow is None:
            raise ValidationError("نام یا نوع دسته را بفرست.")
        direction = self.direction(flow) if flow is not None else None
        await self.lock_book(book_id)
        row = await self.get(book_id, actor_user_id, category_id)
        row = await self.rename(book_id, actor_user_id, category_id, name if name is not None else row.name)
        if direction is not None:
            row.flow = direction
        await self.session.flush()
        return row

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
            raise ValidationError("این نام دسته از قبل وجود دارد.")
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
        ).values(category=name, last_edited_by_id=actor_user_id, last_edited_at=utcnow()))
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

    async def merge(self, book_id, actor_user_id, source_id, target_id):
        """Move everything from ``source`` into ``target`` and drop ``source``.

        This is the way to fold two categories that mean the same thing into one
        without losing or re-typing a single transaction. It reuses what rename
        keeps in step: the name stored on each transaction, the journal memo,
        and the names planning rules hold. Both categories must be the same
        kind of money: folding an expense into an income would silently change
        what the profit figure means.
        """
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        if source_id == target_id:
            raise ValidationError("دستهٔ مبدأ و مقصد یکی است.")
        await self.lock_book(book_id)
        source = await self.get(book_id, actor_user_id, source_id)
        target = await self.get(book_id, actor_user_id, target_id)
        if source.flow is not target.flow:
            raise ValidationError("فقط دسته‌های هم‌نوع (هر دو درآمد یا هر دو هزینه) را می‌شود یکی کرد.")
        # A category budget is unique per target; two budgets for what becomes
        # one category would have to be added together, which is a decision for
        # the owner, not for a merge.
        names = (source.name, target.name)
        budgets = (await self.session.scalars(select(Budget).where(
            Budget.book_id == book_id, Budget.kind == BudgetKind.CATEGORY, Budget.target.in_(names)
        ))).all()
        if len(budgets) > 1:
            raise ValidationError("هر دو دسته بودجه دارند؛ ابتدا یکی را حذف کن.")
        moved = select(Transaction.id).where(
            Transaction.book_id == book_id, Transaction.category_id == source.id
        )
        memo_prefix = "income" if target.flow is Flow.INCOME else "expense"
        await self.session.execute(update(JournalEntry).where(
            JournalEntry.book_id == book_id, JournalEntry.transaction_id.in_(moved)
        ).values(memo=f"{memo_prefix}: {target.name}"))
        await self.session.execute(update(Transaction).where(
            Transaction.book_id == book_id, Transaction.category_id == source.id
        ).values(category=target.name, category_id=target.id,
                 last_edited_by_id=actor_user_id, last_edited_at=utcnow()))
        for model, column in ((Budget, Budget.target), (RecurringRule, RecurringRule.category),
                              (TreasuryRule, TreasuryRule.category)):
            conditions = [model.book_id == book_id, column == source.name]
            if model is Budget:
                conditions.append(Budget.kind == BudgetKind.CATEGORY)
            await self.session.execute(update(model).where(*conditions).values({column.key: target.name}))
        await self.session.delete(source)
        await self.session.flush()
        return target

    async def delete(self, book_id, actor_user_id, category_id):
        await self.books.require(book_id, actor_user_id, Permission.EDIT_TRANSACTION)
        await self.lock_book(book_id)
        row = await self.get(book_id, actor_user_id, category_id)
        if await self.session.scalar(select(Transaction.id).where(
            Transaction.book_id == book_id, Transaction.category_id == category_id
        ).limit(1)):
            raise ValidationError("این دسته تراکنش دارد و قابل حذف نیست.")
        await self.session.delete(row)
        await self.session.flush()
