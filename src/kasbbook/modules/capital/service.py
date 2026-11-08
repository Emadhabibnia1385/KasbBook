"""Assets, rotating funds and what they leave owed.

None of it is income or an expense, so none of it is a transaction: each operation posts a balanced
journal entry between the cash account and an asset or liability account (`posting.post_movement`)
and the wallet's cash follows. Anything that genuinely is income or an expense, a profit on selling
gold or the interest on a loan, is recorded as a normal transaction beside it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.errors import NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..books.models import Permission
from ..books.service import BookService
from ..ledger.models import Flow, JournalEntry, Scope
from ..ledger.service import LedgerService
from ..loans.models import Loan, LoanPayment
from .models import Asset, AssetKind, CapitalMovement, Fund
from .posting import ASSETS, CASH, FUNDS, LOANS, post_movement

GAIN_CATEGORY = "سود فروش دارایی"
LOSS_CATEGORY = "زیان فروش دارایی"


def _positive(value, message: str) -> Decimal:
    amount = quantize(to_decimal(value))
    if amount <= ZERO:
        raise ValidationError(message)
    return amount


@dataclass(frozen=True)
class CapitalOverview:
    """What the book holds and owes beyond cash. Net worth here is these three, not the wallet."""

    assets: Decimal
    fund_claims: Decimal
    liabilities: Decimal

    @property
    def net(self) -> Decimal:
        return self.assets + self.fund_claims - self.liabilities


class CapitalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.ledger = LedgerService(session)

    # ----------------------------------------------------------------- reading
    async def overview(self, book_id: uuid.UUID, user_id: uuid.UUID) -> CapitalOverview:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        await self.ledger.ensure_chart_of_accounts(book_id)
        balance = lambda code: self._balance(book_id, code)  # noqa: E731
        return CapitalOverview(
            assets=quantize(await balance(ASSETS)),
            fund_claims=quantize(await balance(FUNDS)),
            liabilities=quantize(await balance(LOANS)),
        )

    async def _balance(self, book_id: uuid.UUID, code: str) -> Decimal:
        account = await self.ledger.account(book_id, code)
        return await self.ledger.account_balance(account.id)

    async def list_assets(self, book_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[Asset]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Asset).where(Asset.book_id == book_id)
                .order_by(Asset.sold_on.is_not(None), Asset.acquired_on.desc(), Asset.created_at.desc())
            )
        ).scalars().all()

    async def list_funds(self, book_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[Fund]:
        await self.books.require(book_id, user_id, Permission.VIEW_REPORTS)
        return (
            await self.session.execute(
                select(Fund).where(Fund.book_id == book_id).order_by(Fund.starts_on.desc())
            )
        ).scalars().all()

    async def _asset(self, book_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        asset = await self.session.get(Asset, asset_id)
        if asset is None or asset.book_id != book_id:
            raise NotFound("این دارایی پیدا نشد")
        return asset

    async def _fund(self, book_id: uuid.UUID, fund_id: uuid.UUID) -> Fund:
        fund = (
            await self.session.execute(select(Fund).where(Fund.id == fund_id).with_for_update())
        ).scalar_one_or_none()
        if fund is None or fund.book_id != book_id:
            raise NotFound("این صندوق پیدا نشد")
        return fund

    # ------------------------------------------------------------------ assets
    async def buy_asset(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        kind: AssetKind,
        cost,
        on: date,
        down_payment=None,
        installment_amount=None,
        installment_count: Optional[int] = None,
        loan_starts_on: Optional[date] = None,
        quantity=None,
        unit: Optional[str] = None,
        note: Optional[str] = None,
        instrument: Optional[str] = None,
        loan_id: Optional[uuid.UUID] = None,
    ) -> Asset:
        """Buy something that is kept.

        Paid in cash, the money leaves the wallet and becomes the asset. Bought with a loan, the part
        not paid now becomes a debt: the asset and the debt appear together and no cash moves for it.
        Either way nothing is spent: the cost is carried as an asset until it is sold.
        """
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        from ..portfolio.service import describe

        name = (name or "").strip()
        if instrument:
            known = describe(instrument)
            if known is None:
                raise ValidationError("این نوع سرمایه شناخته نشد")
            name = name or known[0]
            unit = unit or known[1]
        if not name:
            raise ValidationError("نام دارایی لازم است")
        price = _positive(cost, "قیمت باید بیشتر از صفر باشد")

        existing: Optional[Loan] = None
        if loan_id is not None:
            if installment_amount is not None or installment_count:
                raise ValidationError("یا یک وام موجود را انتخاب کن یا قسط تازه بنویس، نه هر دو.")
            existing = await self.session.get(Loan, loan_id)
            if existing is None or existing.book_id != book_id:
                raise NotFound("این وام پیدا نشد")
            if existing.kind != "consumer":
                raise ValidationError("این وام قبلاً به یک دارایی وصل شده است.")
            if await self.session.scalar(
                select(LoanPayment.id).where(LoanPayment.loan_id == loan_id).limit(1)
            ):
                raise ValidationError("برای این وام قسط پرداخت شده؛ وامی را انتخاب کن که هنوز قسطی ندارد.")

        financed = existing is None and installment_amount is not None and installment_count
        down = ZERO
        borrowed = ZERO
        if existing is not None:
            down = quantize(to_decimal(down_payment)) if down_payment is not None else ZERO
            if down < ZERO or down >= price:
                raise ValidationError("پیش‌پرداخت باید کمتر از قیمت باشد")
            borrowed = price - down
            if existing.installment_amount * existing.installment_count < borrowed:
                raise ValidationError(
                    "جمع قسط‌های این وام از مبلغ وام کمتر است؛ پیش‌پرداخت را بیشتر کن یا وام دیگری انتخاب کن."
                )
        elif financed:
            each = _positive(installment_amount, "مبلغ قسط باید بیشتر از صفر باشد")
            if int(installment_count) <= 0:
                raise ValidationError("تعداد اقساط باید حداقل 1 باشد")
            down = quantize(to_decimal(down_payment)) if down_payment is not None else ZERO
            if down < ZERO or down >= price:
                raise ValidationError("پیش‌پرداخت باید کمتر از قیمت باشد")
            borrowed = price - down
            if each * int(installment_count) < borrowed:
                raise ValidationError(
                    "جمع قسط‌ها از مبلغ وام کمتر است؛ مبلغ یا تعداد قسط‌ها را بیشتر کن."
                )
        else:
            down = price

        asset = Asset(
            book_id=book_id, name=name[:80], kind=kind, cost=price, acquired_on=on,
            quantity=quantize(to_decimal(quantity)) if quantity is not None else None,
            unit=(unit or None) and unit.strip()[:16], note=note,
            instrument=instrument or None,
        )
        self.session.add(asset)
        if existing is not None:
            existing.kind = "capital"
            existing.principal = borrowed
            await self.session.flush()
            asset.loan_id = existing.id
            asset.loan_linked = True
        elif financed:
            loan = Loan(
                book_id=book_id, title=name[:80], installment_amount=each,
                installment_count=int(installment_count), starts_on=loan_starts_on or on,
                kind="capital", principal=borrowed,
            )
            self.session.add(loan)
            await self.session.flush()
            asset.loan_id = loan.id
        await self.session.flush()

        lines = [(ASSETS, price, ZERO)]
        if down > ZERO:
            lines.append((CASH, ZERO, down))
        if borrowed > ZERO:
            lines.append((LOANS, ZERO, borrowed))
        await post_movement(
            self.session, book_id, user_id, on, "asset_purchase", lines,
            cash_delta=-down, memo=f"خرید دارایی: {asset.name}",
            asset_id=asset.id, loan_id=asset.loan_id,
        )
        return asset

    async def sell_asset(
        self, book_id: uuid.UUID, user_id: uuid.UUID, asset_id: uuid.UUID, price, on: date
    ) -> Asset:
        """Sell it. The cost comes back as cash; what it sold above or below its cost is the only
        income or expense in it, and is recorded as one."""
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        asset = await self._asset(book_id, asset_id)
        if asset.sold_on is not None:
            raise ValidationError("این دارایی قبلاً فروخته شده است.")
        received = _positive(price, "قیمت فروش باید بیشتر از صفر باشد")
        if on < asset.acquired_on:
            raise ValidationError("تاریخ فروش نمی‌تواند پیش از خرید باشد.")

        await post_movement(
            self.session, book_id, user_id, on, "asset_sale",
            [(CASH, asset.cost, ZERO), (ASSETS, ZERO, asset.cost)],
            cash_delta=asset.cost, memo=f"فروش دارایی: {asset.name}", asset_id=asset.id,
        )
        difference = received - asset.cost
        if difference != ZERO:
            await self.ledger.record(
                book_id=book_id, actor_user_id=user_id,
                flow=Flow.INCOME if difference > ZERO else Flow.EXPENSE,
                scope=Scope.PERSONAL,
                category=GAIN_CATEGORY if difference > ZERO else LOSS_CATEGORY,
                amount=abs(difference), occurred_on=on, description=asset.name,
            )
        asset.sold_on = on
        asset.sold_for = received
        await self.session.flush()
        return asset

    async def delete_asset(
        self, book_id: uuid.UUID, user_id: uuid.UUID, asset_id: uuid.UUID
    ) -> None:
        """Take back a purchase that was entered by mistake. Refused once it has history."""
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)
        asset = await self._asset(book_id, asset_id)
        if asset.sold_on is not None:
            raise ValidationError("دارایی فروخته‌شده را نمی‌شود حذف کرد.")
        if asset.loan_id is not None and await self.session.scalar(
            select(LoanPayment.id).where(LoanPayment.loan_id == asset.loan_id).limit(1)
        ):
            raise ValidationError("برای وام این دارایی قسط پرداخت شده؛ حذفش ممکن نیست.")
        await self.ledger._require_open_date(book_id, asset.acquired_on)
        await self._erase_movements(CapitalMovement.asset_id == asset.id)
        loan_id, linked = asset.loan_id, asset.loan_linked
        await self.session.delete(asset)
        await self.session.flush()
        if loan_id is not None:
            loan = await self.session.get(Loan, loan_id)
            if loan is not None and linked:
                # It was a loan of its own before it was tied to this purchase: give it back as it was.
                loan.kind, loan.principal = "consumer", None
            elif loan is not None:
                await self.session.delete(loan)
        await self.session.flush()

    async def _erase_movements(self, condition) -> None:
        rows = (await self.session.execute(select(CapitalMovement).where(condition))).scalars().all()
        for movement in rows:
            if movement.journal_entry_id is not None:
                await self.session.execute(
                    delete(JournalEntry).where(JournalEntry.id == movement.journal_entry_id)
                )
            await self.session.delete(movement)
        await self.session.flush()

    # ------------------------------------------------------------------- funds
    async def create_fund(
        self,
        book_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        monthly_amount,
        months: int,
        payout_amount,
        starts_on: date,
        turn_month: Optional[int] = None,
    ) -> Fund:
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        name = (name or "").strip()
        if not name:
            raise ValidationError("نام صندوق لازم است")
        if int(months) <= 0:
            raise ValidationError("تعداد ماه‌ها باید حداقل 1 باشد")
        if turn_month is not None and not 1 <= int(turn_month) <= int(months):
            raise ValidationError("نوبت باید بین 1 و تعداد ماه‌ها باشد")
        fund = Fund(
            book_id=book_id, name=name[:80],
            monthly_amount=_positive(monthly_amount, "مبلغ ماهانه باید بیشتر از صفر باشد"),
            months=int(months),
            payout_amount=_positive(payout_amount, "مبلغ نوبت باید بیشتر از صفر باشد"),
            starts_on=starts_on, turn_month=int(turn_month) if turn_month else None,
            paid_months=0, claim=ZERO, owed=ZERO,
        )
        self.session.add(fund)
        await self.session.flush()
        return fund

    async def contribute(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID,
        on: date, amount=None,
    ) -> Fund:
        """Pay one month in. Before the turn it builds the claim on the fund; after it, it pays back
        what was received beyond what had been paid in. Never an expense."""
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        fund = await self._fund(book_id, fund_id)
        if fund.paid_months >= fund.months:
            raise ValidationError("همهٔ ماه‌های این صندوق پرداخت شده است.")
        value = _positive(fund.monthly_amount if amount is None else amount,
                          "مبلغ باید بیشتر از صفر باشد")
        if fund.received_on is None:
            await post_movement(
                self.session, book_id, user_id, on, "fund_contribution",
                [(FUNDS, value, ZERO), (CASH, ZERO, value)],
                cash_delta=-value, memo=f"قسط صندوق: {fund.name}", fund_id=fund.id,
            )
            fund.claim = quantize(to_decimal(fund.claim) + value)
        else:
            pay = min(value, to_decimal(fund.owed))
            if pay <= ZERO:
                raise ValidationError("بدهی این صندوق تسویه شده است.")
            await post_movement(
                self.session, book_id, user_id, on, "fund_repayment",
                [(LOANS, pay, ZERO), (CASH, ZERO, pay)],
                cash_delta=-pay, memo=f"بازپرداخت صندوق: {fund.name}", fund_id=fund.id,
            )
            fund.owed = quantize(to_decimal(fund.owed) - pay)
        fund.paid_months += 1
        await self.session.flush()
        return fund

    async def receive_payout(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID,
        on: date, amount=None,
    ) -> Fund:
        """The turn: the pool is paid out. It settles the claim built so far, and the rest is a debt
        to the fund, paid back through the months still to come. Not income."""
        await self.books.require(book_id, user_id, Permission.RECORD_EXPENSE)
        fund = await self._fund(book_id, fund_id)
        if fund.received_on is not None:
            raise ValidationError("نوبت این صندوق قبلاً دریافت شده است.")
        value = _positive(fund.payout_amount if amount is None else amount,
                          "مبلغ باید بیشتر از صفر باشد")
        settled = min(to_decimal(fund.claim), value)
        excess = value - settled
        lines = [(CASH, value, ZERO)]
        if settled > ZERO:
            lines.append((FUNDS, ZERO, settled))
        if excess > ZERO:
            lines.append((LOANS, ZERO, excess))
        await post_movement(
            self.session, book_id, user_id, on, "fund_payout", lines,
            cash_delta=value, memo=f"دریافت نوبت صندوق: {fund.name}", fund_id=fund.id,
        )
        fund.claim = quantize(to_decimal(fund.claim) - settled)
        fund.owed = quantize(to_decimal(fund.owed) + excess)
        fund.received_on = on
        fund.received_amount = value
        await self.session.flush()
        return fund

    async def delete_fund(
        self, book_id: uuid.UUID, user_id: uuid.UUID, fund_id: uuid.UUID
    ) -> None:
        """A fund nobody has paid into or drawn from can be removed; one with history cannot."""
        await self.books.require(book_id, user_id, Permission.DELETE_TRANSACTION)
        fund = await self._fund(book_id, fund_id)
        moved = await self.session.scalar(
            select(func.count(CapitalMovement.id)).where(CapitalMovement.fund_id == fund.id)
        )
        if moved or fund.paid_months or fund.received_on is not None:
            raise ValidationError("این صندوق سابقه دارد و حذف نمی‌شود.")
        await self.session.delete(fund)
        await self.session.flush()

    # ----------------------------------------------------------------- wallet
    async def cash_effect(self, book_id: uuid.UUID) -> Decimal:
        """The cash these movements have moved in the book's currency, for the wallet."""
        rows = (
            await self.session.execute(
                select(CapitalMovement.cash_delta).where(CapitalMovement.book_id == book_id)
            )
        ).scalars().all()
        return quantize(sum((to_decimal(value) for value in rows), ZERO))
