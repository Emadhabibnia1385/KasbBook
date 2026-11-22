"""Writing a person's income from a team or business book into their own book, and keeping it true.

The design in one paragraph. A link says which source book, which of my books, and *when* the income
counts. Every moment the source can change (a payment, a period closing, a transaction on a day) calls
back here, and the answer is always recomputed from the source rather than adjusted by what changed:
"what should my book hold for this payment / period / day?" is compared with the entry that exists and
the entry is created, updated or removed to match. So a late income on a day already written simply
changes that day's amount; a voided payment removes its income; running it twice writes nothing twice.

It is best effort by design: a closed period or a lost permission in the target book must never stop a
payroll payment or a team's own entry. The refusal is kept on the entry as a `problem`, shown to the
person, and a resync tries again.

Modes are cash and accrual, named for what they are: `payment` is cash (the day the team pays me),
`period` is settlement (my net pay, when the payroll period closes), and `daily`/`weekly`/`monthly` are a
running share of the book's net income (income minus costs) for that day, week or month. The running ones
are dated the last day in the bucket that had income, so nothing is ever dated in the future.
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import calendars, jalali
from ...shared.errors import KasbBookError, NotFound, ValidationError
from ...shared.money import ZERO, quantize, to_decimal
from ..banks.service import UNSET
from ..books.models import Book, BookType, Permission
from ..books.service import BookService
from ..capital.models import CapitalMovement
from ..ledger.models import Flow, JournalEntry, Scope, Transaction
from ..ledger.service import LedgerService
from ..payroll.models import FinancialPeriod, Payment, Payslip, PeriodStatus, ShareBasis
from .models import BUCKETS, DAILY, MODES, MONTHLY, PAYMENT, PERIOD, WEEKLY, IncomeEntry, IncomeLink

# True while the sync itself is writing, so what it writes cannot start another sync.
_syncing: contextvars.ContextVar[bool] = contextvars.ContextVar("income_syncing", default=False)

NOT_FOUND = "این پیوند پیدا نشد."
# The account that stands against cash an owner takes out of their business, or puts back in.
DRAW = "3400"
HUNDRED = Decimal("100")


@dataclass
class LinkView:
    link: IncomeLink
    source_name: str
    target_name: str
    entries: int
    problems: int
    total: Decimal
    # Plain sentences about why nothing (or not everything) was written: a start day that has not come, or
    # transactions from before it. Empty when there is nothing to explain.
    notes: List[str]


def _bucket(mode: str, day: date, cal) -> Tuple[str, date, date]:
    """(ref, first day, last day) of the day, week or month a date falls in."""
    if mode == DAILY:
        return f"day:{day.isoformat()}", day, day
    if mode == WEEKLY:
        start, end = cal.week_range(today=day)
        return f"week:{start.isoformat()}", start, end
    year, month, _ = cal.to_parts(day)
    start, end = cal.month_range(year, month)
    return f"month:{start.isoformat()}", start, end


def _bucket_of_ref(ref: str, cal) -> Tuple[date, date]:
    kind, _, text = ref.partition(":")
    first = date.fromisoformat(text)
    return _bucket({"day": DAILY, "week": WEEKLY, "month": MONTHLY}[kind], first, cal)[1:]


class IncomeSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = BookService(session)
        self.ledger = LedgerService(session)

    # ------------------------------------------------------------------ links
    async def _mine(self, user_id: uuid.UUID, link_id: uuid.UUID) -> IncomeLink:
        link = await self.session.scalar(select(IncomeLink).where(
            IncomeLink.id == link_id, IncomeLink.user_id == user_id
        ).execution_options(populate_existing=True))
        if link is None:
            raise NotFound(NOT_FOUND)
        return link

    async def create_link(
        self, actor_id: uuid.UUID, *, source_book_id: uuid.UUID, target_book_id: uuid.UUID,
        mode: str, category: Optional[str] = None, starts_on: Optional[date] = None,
        bank_account_id=UNSET, draws: Optional[bool] = None,
    ) -> IncomeLink:
        if mode not in MODES:
            raise ValidationError("حالت همگام‌سازی باید یکی از «هر پرداخت»، «پایان دوره»، «روزانه»، «هفتگی» یا «ماهانه» باشد.")
        if source_book_id == target_book_id:
            raise ValidationError("دفتر مبدأ و مقصد باید دو دفتر متفاوت باشند.")
        await self.books.require(source_book_id, actor_id, Permission.VIEW_REPORTS)
        await self.books.require(target_book_id, actor_id, Permission.RECORD_INCOME)
        source = await self.books.get_book(source_book_id)
        target = await self.books.get_book(target_book_id)
        if target.owner_user_id != actor_id or target.type not in (BookType.PERSONAL, BookType.BUSINESS):
            raise ValidationError("درآمد را فقط در دفتر شخصی یا کسب‌وکار خودت می‌شود نوشت.")
        if source.base_currency != target.base_currency:
            raise ValidationError("واحد اصلی این دو دفتر یکی نیست؛ درآمد بین‌شان منتقل نمی‌شود.")
        if source.type is BookType.PERSONAL:
            raise ValidationError("از یک دفتر شخصی درآمد منتقل نمی‌شود؛ مبدأ باید دفتر تیمی، سازمانی یا کسب‌وکار باشد.")
        if source.type is BookType.BUSINESS:
            if source.owner_user_id != actor_id:
                raise ValidationError("درآمد دفتر کسب‌وکار را فقط صاحب آن می‌تواند منتقل کند.")
            if mode not in BUCKETS:
                raise ValidationError("دفتر کسب‌وکار حقوق ندارد؛ حالت روزانه، هفتگی یا ماهانه را انتخاب کن.")
        elif mode in BUCKETS:
            rule = (await self._payroll().share_rules_for(
                source_book_id, jalali.today_in(source.timezone))).get(actor_id)
            if rule is not None and rule.basis is not ShareBasis.PERCENT:
                raise ValidationError(
                    "سهم تو درصدی نیست؛ حالت روزانه، هفتگی و ماهانه فقط برای سهم درصدی است. "
                    "«هر پرداخت» یا «پایان دوره» را انتخاب کن."
                )
        # One hop only: a book that feeds another cannot itself be fed, or two links could chase each other.
        chained = await self.session.scalar(select(IncomeLink.id).where(
            (IncomeLink.target_book_id == source_book_id) | (IncomeLink.source_book_id == target_book_id)
        ).limit(1))
        if chained is not None:
            raise ValidationError("این دفتر خودش در یک پیوند درآمد است؛ پیوند زنجیره‌ای ساخته نمی‌شود.")
        if await self.session.scalar(select(IncomeLink.id).where(
            IncomeLink.source_book_id == source_book_id, IncomeLink.user_id == actor_id
        ).limit(1)):
            raise ValidationError("برای این دفتر قبلاً پیوند ساخته‌ای؛ همان را تغییر بده.")
        # A business of one takes its owner's income out of itself by default, so what the business holds
        # follows what its owner took; a team pays its members through payroll instead and has no draw.
        takes = source.type is BookType.BUSINESS if draws is None else bool(draws)
        if takes and source.type is not BookType.BUSINESS:
            raise ValidationError("برداشت از دفتر مبدأ فقط برای دفتر کسب‌وکار است؛ تیم از راه حقوق پرداخت می‌کند.")
        link_bank = await self.ledger.banks.resolve(target_book_id, bank_account_id, in_base_currency=True)
        # Left empty, the income is filed under the name of the book it comes from.
        name = (category or "").strip() or source.name.strip()
        if len(name) > 80:
            raise ValidationError("نام دسته حداکثر 80 حرف است.")
        link = IncomeLink(
            source_book_id=source_book_id, target_book_id=target_book_id, user_id=actor_id, mode=mode,
            category=name, starts_on=starts_on or jalali.today_in(target.timezone),
            bank_account_id=link_bank.bank_account_id if link_bank else None, is_active=True,
            draws=takes,
        )
        self.session.add(link)
        await self.session.flush()
        await self._resync(link)
        return link

    async def update_link(
        self, actor_id: uuid.UUID, link_id: uuid.UUID, *, mode=UNSET, category=UNSET,
        starts_on=UNSET, is_active=UNSET, draws=UNSET,
    ) -> IncomeLink:
        link = await self._mine(actor_id, link_id)
        rebuild = False
        if mode is not UNSET and mode != link.mode:
            if mode not in MODES:
                raise ValidationError("حالت همگام‌سازی نامعتبر است.")
            source = await self.books.get_book(link.source_book_id)
            if source.type is BookType.BUSINESS and mode not in BUCKETS:
                raise ValidationError("دفتر کسب‌وکار حقوق ندارد؛ حالت روزانه، هفتگی یا ماهانه را انتخاب کن.")
            # A different rhythm means different entries: the old ones are taken back, then written anew.
            await self._clear(link)
            link.mode = mode
            rebuild = True
        if category is not UNSET:
            name = (category or "").strip()
            if not name or len(name) > 80:
                raise ValidationError("نام دسته باید بین 1 تا 80 حرف باشد.")
            link.category = name
            await self._recategorise(link)
        if starts_on is not UNSET and starts_on is not None and starts_on != link.starts_on:
            link.starts_on = starts_on
            rebuild = True
        if draws is not UNSET:
            if draws is None:
                raise ValidationError("برداشت را روشن یا خاموش کن.")
            if draws and (await self.books.get_book(link.source_book_id)).type is not BookType.BUSINESS:
                raise ValidationError("برداشت از دفتر مبدأ فقط برای دفتر کسب‌وکار است؛ تیم از راه حقوق پرداخت می‌کند.")
            if bool(draws) != link.draws:
                link.draws = bool(draws)
                rebuild = True
        if is_active is not UNSET:
            if is_active is None:
                raise ValidationError("فعال یا غیرفعال را مشخص کن.")
            rebuild = rebuild or (bool(is_active) and not link.is_active)
            link.is_active = bool(is_active)
        await self.session.flush()
        if rebuild and link.is_active:
            await self._resync(link)
        return link

    async def delete_link(self, actor_id: uuid.UUID, link_id: uuid.UUID, *, remove_income: bool = False) -> None:
        """End the link. The income already written stays in the book as ordinary transactions unless asked."""
        link = await self._mine(actor_id, link_id)
        if remove_income:
            await self._clear(link)
        await self.session.delete(link)
        await self.session.flush()

    async def mine(self, user_id: uuid.UUID) -> List[LinkView]:
        links = (await self.session.scalars(
            select(IncomeLink).where(IncomeLink.user_id == user_id).order_by(IncomeLink.created_at)
        )).all()
        out: List[LinkView] = []
        for link in links:
            entries = (await self.session.scalars(
                select(IncomeEntry).where(IncomeEntry.link_id == link.id)
            )).all()
            out.append(LinkView(
                link=link,
                source_name=(await self.books.get_book(link.source_book_id)).name,
                target_name=(await self.books.get_book(link.target_book_id)).name,
                entries=sum(1 for e in entries if e.transaction_id is not None),
                problems=sum(1 for e in entries if e.problem),
                total=sum((e.amount for e in entries if e.transaction_id is not None), ZERO),
                notes=await self._notes(link, entries),
            ))
        return out

    async def _notes(self, link: IncomeLink, entries: Sequence[IncomeEntry]) -> List[str]:
        """Why nothing, or not everything, was written, in the words a person would use.

        The panel used to say only «هنوز درآمدی نوشته نشده» and leave the person to guess. The usual cause is
        a start day: later than today, or later than the transactions they meant.
        """
        source = await self.books.get_book(link.source_book_id)
        cal = calendars.of(source)
        notes: List[str] = []
        member = await self.books.membership(link.source_book_id, link.user_id)
        if member is None or not member.is_active:
            notes.append("دیگر عضو دفتر مبدأ نیستی؛ چیز تازه‌ای نوشته نمی‌شود و آنچه نوشته شده می‌ماند.")
        if not link.is_active:
            notes.append("این پیوند غیرفعال است؛ تا فعالش نکنی چیزی نوشته نمی‌شود.")
        today = jalali.today_in(source.timezone)
        if link.starts_on > today:
            notes.append(
                f"تاریخ شروع ({cal.to_text(link.starts_on)}) هنوز نرسیده؛ تا آن روز چیزی نوشته نمی‌شود."
            )
        before = (await self.session.execute(
            select(func.count(Transaction.id), func.min(Transaction.occurred_on), func.max(Transaction.occurred_on))
            .where(Transaction.book_id == link.source_book_id, Transaction.occurred_on < link.starts_on)
        )).one()
        if before[0]:
            notes.append(
                f"{before[0]} تراکنش از {cal.to_text(before[1])} تا {cal.to_text(before[2])} پیش از تاریخ شروع‌اند "
                "و نوشته نمی‌شوند؛ برای نوشتنشان «از چه روزی» را عقب‌تر ببر."
            )
        if link.mode in BUCKETS and source.type is not BookType.BUSINESS:
            rule = (await self._payroll().share_rules_for(source.id, max(today, link.starts_on))).get(link.user_id)
            if rule is None:
                notes.append("برای تو در این دفتر سهم درصدی تعریف نشده یا هنوز شروع نشده؛ بدون آن چیزی نوشته نمی‌شود.")
            elif rule.basis is not ShareBasis.PERCENT:
                notes.append("سهم تو درصدی نیست؛ این حالت فقط برای سهم درصدی است.")
        if not entries and not notes:
            notes.append(
                "در بازهٔ پس از تاریخ شروع تراکنشی که درآمد خالص یا زیانی بسازد پیدا نشد؛ با ثبت درآمد یا هزینه "
                "در دفتر مبدأ اینجا پر می‌شود."
            )
        return notes

    async def entries(self, user_id: uuid.UUID, link_id: uuid.UUID) -> List[IncomeEntry]:
        link = await self._mine(user_id, link_id)
        return list((await self.session.scalars(
            select(IncomeEntry).where(IncomeEntry.link_id == link.id)
            .order_by(IncomeEntry.occurred_on.desc(), IncomeEntry.ref.desc())
        )).all())

    async def resync(self, user_id: uuid.UUID, link_id: uuid.UUID) -> IncomeLink:
        """Work it all out again from the source: catches up, retries what the book refused."""
        link = await self._mine(user_id, link_id)
        if not link.is_active:
            raise ValidationError("این پیوند غیرفعال است؛ اول فعالش کن.")
        await self._resync(link)
        return link

    # ------------------------------------------------------- what the source calls
    async def touch(self, book_id: uuid.UUID, days) -> None:
        """A transaction changed in a book on these days: bring the running links that read it up to date."""
        if _syncing.get():
            return
        links = (await self.session.scalars(select(IncomeLink).where(
            IncomeLink.source_book_id == book_id, IncomeLink.is_active.is_(True),
            IncomeLink.mode.in_(BUCKETS),
        ))).all()
        if not links:
            return
        cal = calendars.of(await self.books.get_book(book_id))
        for link in links:
            refs = {_bucket(link.mode, day, cal)[0] for day in days if day and day >= link.starts_on}
            if refs:
                await self._resync(link, only=refs)

    async def payroll_changed(self, book_id: uuid.UUID) -> None:
        """A payment, a void, a close or a reopen happened in a book's payroll."""
        if _syncing.get():
            return
        links = (await self.session.scalars(select(IncomeLink).where(
            IncomeLink.source_book_id == book_id, IncomeLink.is_active.is_(True),
            IncomeLink.mode.in_((PAYMENT, PERIOD)),
        ))).all()
        for link in links:
            await self._resync(link)

    # ------------------------------------------------------------------ the work
    def _payroll(self):
        from ..payroll.service import PayrollService  # here, not at the top: payroll calls back into this module

        return PayrollService(self.session)

    async def _resync(self, link: IncomeLink, only: Optional[Set[str]] = None) -> None:
        member = await self.books.membership(link.source_book_id, link.user_id)
        if member is None or not member.is_active:
            # Someone who left the team keeps the income already written; nothing more arrives.
            return
        token = _syncing.set(True)
        try:
            wanted = await self._expected(link, only)
            if only is not None:
                refs = set(only)
            else:
                refs = set(wanted) | set((await self.session.scalars(
                    select(IncomeEntry.ref).where(IncomeEntry.link_id == link.id)
                )).all())
            for ref in sorted(refs):
                await self._apply(link, ref, wanted.get(ref))
        finally:
            _syncing.reset(token)

    async def _expected(
        self, link: IncomeLink, only: Optional[Set[str]]
    ) -> Dict[str, Tuple[date, Decimal, str]]:
        """ref -> (day, amount, label) for everything the source says the target should hold."""
        if link.mode == PAYMENT:
            rows = (await self.session.execute(
                select(Payment, Payslip).join(Payslip, Payslip.id == Payment.payslip_id).where(
                    Payslip.book_id == link.source_book_id, Payslip.user_id == link.user_id,
                    Payment.paid_on >= link.starts_on,
                )
            )).all()
            out = {}
            for payment, slip in rows:
                value = quantize(payment.amount * payment.conversion_rate)
                if value > ZERO:
                    out[f"pay:{payment.id}"] = (payment.paid_on, value, "پرداخت")
            return out
        if link.mode == PERIOD:
            rows = (await self.session.execute(
                select(Payslip, FinancialPeriod).join(FinancialPeriod, FinancialPeriod.id == Payslip.period_id)
                .where(
                    Payslip.book_id == link.source_book_id, Payslip.user_id == link.user_id,
                    FinancialPeriod.status == PeriodStatus.LOCKED, FinancialPeriod.ends_on >= link.starts_on,
                )
            )).all()
            return {
                f"period:{period.id}": (period.ends_on, quantize(slip.net_pay), period.label)
                for slip, period in rows if quantize(slip.net_pay) > ZERO
            }
        return await self._running(link, only)

    async def _running(self, link: IncomeLink, only: Optional[Set[str]]):
        source = await self.books.get_book(link.source_book_id)
        cal = calendars.of(source)
        stmt = select(Transaction).where(
            Transaction.book_id == link.source_book_id, Transaction.occurred_on >= link.starts_on
        )
        if only is not None:
            spans = [_bucket_of_ref(ref, cal) for ref in only]
            stmt = stmt.where(
                Transaction.occurred_on >= min(start for start, _ in spans),
                Transaction.occurred_on <= max(end for _, end in spans),
            )
        buckets: Dict[str, Dict[str, object]] = {}
        for tx in (await self.session.scalars(stmt)).all():
            ref, start, _ = _bucket(link.mode, tx.occurred_on, cal)
            if only is not None and ref not in only:
                continue
            slot = buckets.setdefault(ref, {"income": ZERO, "costs": ZERO, "last": None, "any": None})
            if slot["any"] is None or tx.occurred_on > slot["any"]:  # type: ignore[operator]
                slot["any"] = tx.occurred_on
            if tx.flow is Flow.INCOME:
                slot["income"] += tx.converted_amount  # type: ignore[operator]
                if slot["last"] is None or tx.occurred_on > slot["last"]:  # type: ignore[operator]
                    slot["last"] = tx.occurred_on
            else:
                slot["costs"] += tx.converted_amount  # type: ignore[operator]
        out: Dict[str, Tuple[date, Decimal, str]] = {}
        for ref, slot in buckets.items():
            # Signed, never clamped: a day whose costs are more than its income is a loss for this person's
            # share, and writing it as zero (or as nothing) made the days add up to something other than
            # their share of the book's profit whenever the costs fell on a different day from the income.
            net = slot["income"] - slot["costs"]  # type: ignore[operator]
            if net == ZERO:
                continue
            # A gain is dated the last day with income, so it is never in the future; a loss, the last day
            # with anything at all.
            day = slot["last"] if net > ZERO else slot["any"]
            percent = await self._percent(link, source, day)  # type: ignore[arg-type]
            amount = quantize(net * percent / HUNDRED)
            if amount != ZERO:
                out[ref] = (day, amount, ref.split(":", 1)[1])  # type: ignore[arg-type]
        return out

    async def _percent(self, link: IncomeLink, source: Book, on: date) -> Decimal:
        """This person's share of the book's net income on a day: all of it for their own business, else their percentage."""
        if source.type is BookType.BUSINESS:
            return HUNDRED if source.owner_user_id == link.user_id else ZERO
        rule = (await self._payroll().share_rules_for(source.id, on)).get(link.user_id)
        if rule is None or rule.basis is not ShareBasis.PERCENT:
            return ZERO
        return Decimal(rule.value)

    async def _apply(self, link: IncomeLink, ref: str, want: Optional[Tuple[date, Decimal, str]]) -> None:
        entry = await self.session.scalar(select(IncomeEntry).where(
            IncomeEntry.link_id == link.id, IncomeEntry.ref == ref
        ).execution_options(populate_existing=True))
        if want is None:
            if entry is not None:
                await self._remove(link, entry)
            return
        on, amount, label = want
        # A positive amount is income; a negative one is this person's share of costs, written as an expense
        # so that, added up, the entries are exactly their share of the book's net.
        flow = Flow.INCOME if amount > ZERO else Flow.EXPENSE
        magnitude = abs(amount)
        target = await self.books.get_book(link.target_book_id)
        source = await self.books.get_book(link.source_book_id)
        note = (f"همگام‌شده از «{source.name}» — {label}" if flow is Flow.INCOME
                else f"سهم از هزینه‌های «{source.name}» — {label}")
        if entry is None:
            entry = IncomeEntry(link_id=link.id, ref=ref, occurred_on=on, amount=amount)
            self.session.add(entry)
            await self.session.flush()
        tx = await self.session.get(Transaction, entry.transaction_id) if entry.transaction_id else None
        try:
            async with self.session.begin_nested():
                if tx is None:
                    tx = await self.ledger.record(
                        link.target_book_id, link.user_id, flow,
                        Scope.PERSONAL if target.type is BookType.PERSONAL else Scope.WORK,
                        link.category, magnitude, occurred_on=on, description=note,
                        bank_account_id=link.bank_account_id,
                    )
                    entry.transaction_id = tx.id
                elif tx.converted_amount != magnitude or tx.occurred_on != on or tx.flow is not flow:
                    await self.ledger.update(
                        link.target_book_id, link.user_id, tx.id, amount=magnitude, occurred_on=on,
                        flow=flow, description=note,
                    )
                # The same amount leaves the business as the owner's draw, in the same step: either both
                # are written or the entry says why neither was.
                await self._sync_draw(link, entry, source, on, amount)
            entry.problem = None
        except KasbBookError as error:
            # Kept, not raised: a closed month in the target must never stop a payment or an entry here.
            entry.problem = str(error)[:300]
        entry.occurred_on, entry.amount = on, amount
        await self.session.flush()

    async def _sync_draw(
        self, link: IncomeLink, entry: IncomeEntry, source: Book, on: date, amount: Decimal
    ) -> None:
        """Keep the source business's draw in step with the entry: what the owner took out, as cash leaving
        the book (not an expense, so its profit is untouched), or put back when the share was a loss."""
        movement = (
            await self.session.get(CapitalMovement, entry.draw_movement_id)
            if entry.draw_movement_id else None
        )
        if not link.draws:
            if movement is not None:
                await self._erase_draw(entry, movement)
            return
        cash = -amount
        if movement is not None and movement.occurred_on == on and to_decimal(movement.cash_delta) == cash:
            return
        if movement is not None:
            await self._erase_draw(entry, movement)
        from ..capital.posting import CASH, post_movement

        value = abs(amount)
        lines = ([(DRAW, value, ZERO), (CASH, ZERO, value)] if amount > ZERO
                 else [(CASH, value, ZERO), (DRAW, ZERO, value)])
        moved = await post_movement(
            self.session, link.source_book_id, link.user_id, on, "owner_draw", lines,
            cash_delta=cash, memo=f"برداشت مالک از «{source.name}»",
        )
        entry.draw_movement_id = moved.id

    async def _erase_draw(self, entry: IncomeEntry, movement: CapitalMovement) -> None:
        if movement.journal_entry_id is not None:
            journal = await self.session.get(JournalEntry, movement.journal_entry_id)
            if journal is not None:
                await self.session.delete(journal)
        await self.session.delete(movement)
        entry.draw_movement_id = None
        await self.session.flush()

    async def _remove(self, link: IncomeLink, entry: IncomeEntry) -> None:
        if entry.draw_movement_id is not None:
            movement = await self.session.get(CapitalMovement, entry.draw_movement_id)
            if movement is not None:
                try:
                    async with self.session.begin_nested():
                        await self._erase_draw(entry, movement)
                except KasbBookError as error:
                    entry.problem = str(error)[:300]
                    await self.session.flush()
                    return
        if entry.transaction_id is not None:
            try:
                async with self.session.begin_nested():
                    await self.ledger.delete(link.target_book_id, link.user_id, entry.transaction_id)
            except KasbBookError as error:
                entry.problem = str(error)[:300]
                await self.session.flush()
                return
            # The entry went with its transaction (ON DELETE CASCADE); the session still holds the object.
            self.session.expunge(entry)
            return
        await self.session.delete(entry)
        await self.session.flush()

    async def _clear(self, link: IncomeLink) -> None:
        token = _syncing.set(True)
        try:
            for entry in (await self.session.scalars(
                select(IncomeEntry).where(IncomeEntry.link_id == link.id)
            )).all():
                await self._remove(link, entry)
        finally:
            _syncing.reset(token)

    async def _recategorise(self, link: IncomeLink) -> None:
        token = _syncing.set(True)
        try:
            for entry in (await self.session.scalars(
                select(IncomeEntry).where(IncomeEntry.link_id == link.id, IncomeEntry.transaction_id.is_not(None))
            )).all():
                try:
                    async with self.session.begin_nested():
                        await self.ledger.update(
                            link.target_book_id, link.user_id, entry.transaction_id, category=link.category
                        )
                except KasbBookError as error:
                    entry.problem = str(error)[:300]
        finally:
            _syncing.reset(token)
        await self.session.flush()


__all__ = ["IncomeSyncService", "LinkView"]
