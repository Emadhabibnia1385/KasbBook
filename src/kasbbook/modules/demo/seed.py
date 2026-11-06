# -*- coding: utf-8 -*-
"""A demo workspace: four books of a year's worth of believable data, so the whole panel can be seen.

Everything here goes through the same services the panel and the bot use, so the journal balances, the
wallets follow, the reports add up and the rules (permissions, periods, funds) are the real ones. Only the
figures are made up. The dates are relative to today, so the current month is always the last one filled.

There is one such account for everybody (`ensure_demo`): it is a guest account, so it can keep nothing
lasting, but signing out of it does not remove it. It is renewed once it is a couple of weeks old, so the
months it shows stay the latest ones; renewing removes every book and made-up colleague first.
"""

from __future__ import annotations

import calendar as pycal
import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared import jalali
from ..books.models import BookType, Membership, Role
from ..books.service import BookService
from ..budgets.models import BudgetKind
from ..budgets.service import BudgetService
from ..capital.service import CapitalService
from ..capital.models import AssetKind
from ..debts.models import Direction
from ..debts.service import DebtService
from ..exchange.service import ExchangeService
from ...shared.security import utcnow
from ..identity.models import DEMO_USERNAME, User
from ..identity.service import IdentityService
from ..ledger.categories import CategoryService
from ..ledger.models import Flow, Scope
from ..ledger.service import LedgerService
from ..loans.service import LoanService
from ..payroll.models import ShareBasis
from ..payroll.service import PayrollService
from ..portfolio.service import PortfolioService
from ..recurring.models import Mode, Period
from ..recurring.service import RecurringService
from ..treasury.models import FundKind, RuleBasis
from ..treasury.service import TreasuryService

DEMO_NAME = "کاربر دمو"
DEMO_LIFETIME_DAYS = 14
SCOPE_OF = {
    BookType.PERSONAL: Scope.PERSONAL,
    BookType.BUSINESS: Scope.WORK,
    BookType.TEAM: Scope.TEAM,
    BookType.ORGANIZATION: Scope.TEAM,
}


def _round(value: float, step: int = 10_000) -> int:
    return max(step, int(round(value / step)) * step)


@dataclass
class Month:
    start: date
    end: date           # the last day of the month, or today for the current one
    label: str
    index: int          # 0 is the oldest of the twelve


def jalali_months(today: date, count: int = 12) -> List[Month]:
    out: List[Month] = []
    for i, (y, m) in enumerate(jalali.recent_months(count, today)):
        start, end = jalali.month_range(y, m)
        out.append(Month(start, min(end, today), f"{jalali.month_name(m)} {y}", i))
    return out


def gregorian_months(today: date, count: int = 12) -> List[Month]:
    out: List[Month] = []
    for i in range(count):
        back = count - 1 - i
        total = today.year * 12 + (today.month - 1) - back
        y, m = divmod(total, 12)
        m += 1
        start = date(y, m, 1)
        end = date(y, m, pycal.monthrange(y, m)[1])
        out.append(Month(start, min(end, today), f"{y}-{m:02d}", i))
    return out


class Seeder:
    def __init__(self, session: AsyncSession, today: date, seed: int = 1405) -> None:
        self.session = session
        self.today = today
        self.rng = random.Random(seed)
        self.books = BookService(session)
        self.ledger = LedgerService(session)
        self.exchange = ExchangeService(session)
        self.rows = 0

    # ------------------------------------------------------------------ helpers
    def usdt_rate(self, on: date) -> Decimal:
        """A believable toman price of a tether over the year: 185,000 climbing to 270,000, with noise."""
        span = max(1, (self.today - (self.today - timedelta(days=365))).days)
        progress = 1 - (self.today - on).days / span
        base = 185_000 + 85_000 * max(0.0, min(1.0, progress))
        return Decimal(_round(base * self.rng.uniform(0.985, 1.015), 100))

    def days(self, month: Month, n: int, low: int = 1, high: int = 28) -> List[date]:
        """`n` distinct days of the month, in order, never after today."""
        last = (month.end - month.start).days + 1
        pool = [d for d in range(low, min(high, last) + 1)]
        picks = sorted(self.rng.sample(pool, min(n, len(pool)))) if pool else []
        return [month.start + timedelta(days=d - 1) for d in picks if month.start + timedelta(days=d - 1) <= self.today]

    def day(self, month: Month, number: int) -> Optional[date]:
        on = month.start + timedelta(days=number - 1)
        return on if on <= min(month.end, self.today) else None

    async def tx(self, book, owner: User, flow: Flow, category: str, amount, on: Optional[date],
                 description: Optional[str] = None, currency: Optional[str] = None, rate=None) -> None:
        if on is None or on > self.today:
            return
        await self.ledger.record(
            book.id, owner.id, flow, SCOPE_OF[book.type], category, amount, occurred_on=on,
            description=description, currency=currency, conversion_rate=rate,
        )
        self.rows += 1

    async def spread(self, book, owner, months: Sequence[Month], flow: Flow, rows: Sequence[tuple]) -> None:
        """rows of (category, per month, low, high, descriptions, growth per month)."""
        for month in months:
            for category, per, low, high, notes, growth in rows:
                count = per if isinstance(per, int) else self.rng.choice(per)
                for on in self.days(month, count):
                    amount = _round(self.rng.uniform(low, high) * (1 + growth * month.index))
                    await self.tx(book, owner, flow, category, amount, on, self.rng.choice(notes))

    async def make_book(self, owner: User, name: str, kind: BookType, calendar: str = "jalali"):
        book = await self.books.create_book(owner.id, name, kind, "IRT", calendar=calendar)
        return book

    async def add_member(self, book, name: str, role: Role) -> User:
        member = User(display_name=name)
        self.session.add(member)
        await self.session.flush()
        self.session.add(Membership(book_id=book.id, user_id=member.id, role=role, joined_at=jalali_now()))
        await self.session.flush()
        return member

    async def extra_categories(self, book, owner, flow: Flow, names: Sequence[str]) -> None:
        cats = CategoryService(self.session)
        for name in names:
            await cats.create(book.id, owner.id, name, flow)

    # ----------------------------------------------------------------- the books
    async def personal(self, owner: User) -> None:
        book = await self.make_book(owner, "حساب‌داری شخصی", BookType.PERSONAL)
        months = jalali_months(self.today)
        await self.exchange.set_enabled(owner.id, book.id, "USDT", True)
        await self.exchange.set_enabled(owner.id, book.id, "USD", True)

        # income
        for month in months:
            await self.tx(book, owner, Flow.INCOME, "حقوق", 38_000_000 if month.index < 6 else 43_500_000,
                          self.day(month, 1), "حقوق ماهانه")
            await self.tx(book, owner, Flow.INCOME, "سود سپرده", _round(self.rng.uniform(520_000, 640_000), 1000),
                          self.day(month, 5), "سود ماهانه سپردهٔ کوتاه‌مدت")
            if month.index % 2 == 1:
                await self.tx(book, owner, Flow.INCOME, "فریلنس", _round(self.rng.uniform(4e6, 12e6), 100_000),
                              self.day(month, self.rng.randint(8, 24)), self.rng.choice(
                                  ["طراحی لوگو برای مشتری", "مشاورهٔ پروژه", "ترجمهٔ فنی", "بازبینی کد"]))
        await self.tx(book, owner, Flow.INCOME, "عیدی و پاداش", 52_000_000, self.day(months[1], 12), "پاداش پایان سال")
        await self.tx(book, owner, Flow.INCOME, "سهم ارث", 320_000_000, self.day(months[3], 10), "سهم از فروش زمین پدری")

        # everyday expenses
        await self.spread(book, owner, months, Flow.EXPENSE, [
            ("اجارهٔ خانه", 1, 14_000_000, 14_000_000, ["اجارهٔ ماهانه"], 0.0),
            ("خرید خانه", [4, 5], 600_000, 2_300_000, ["سوپرمارکت", "خرید هفتگی", "میوه و تره‌بار", "نانوایی و لبنیات"], 0.012),
            ("رستوران و کافه", [3, 4], 350_000, 1_900_000, ["شام بیرون", "کافه با دوستان", "ناهار کاری", "سفارش آنلاین غذا"], 0.01),
            ("حمل‌ونقل", [3, 4], 120_000, 650_000, ["اسنپ", "تاکسی", "مترو و اتوبوس"], 0.015),
            ("سوخت", 1, 700_000, 1_100_000, ["بنزین"], 0.02),
            ("قبض برق و گاز", 1, 450_000, 1_400_000, ["قبض برق", "قبض گاز", "قبض آب"], 0.0),
            ("اینترنت و موبایل", 2, 380_000, 720_000, ["اینترنت خانگی", "شارژ سیم‌کارت"], 0.01),
            ("سلامت و دارو", [1, 2], 250_000, 2_800_000, ["داروخانه", "ویزیت پزشک", "آزمایش", "دندان‌پزشکی"], 0.01),
            ("تفریح و سینما", [1, 2], 300_000, 1_500_000, ["سینما", "کنسرت", "بازی و سرگرمی"], 0.0),
            ("اشتراک‌ها", 2, 190_000, 520_000, ["نتفلیکس", "اسپاتیفای", "ذخیرهٔ ابری"], 0.0),
        ])
        for month in months:
            if month.index % 2 == 0:
                await self.tx(book, owner, Flow.EXPENSE, "پوشاک", _round(self.rng.uniform(1.5e6, 6e6), 100_000),
                              self.day(month, self.rng.randint(5, 25)), self.rng.choice(["لباس زمستانی", "کفش", "پیراهن و شلوار"]))
            if month.index % 3 == 1:
                await self.tx(book, owner, Flow.EXPENSE, "آموزش", _round(self.rng.uniform(1.2e6, 3.5e6), 100_000),
                              self.day(month, self.rng.randint(3, 20)), self.rng.choice(["دورهٔ آنلاین", "کتاب", "کلاس زبان"]))
            if month.index % 3 == 2:
                await self.tx(book, owner, Flow.EXPENSE, "بیمه", 4_200_000, self.day(month, 15), "بیمهٔ تکمیلی و شخص ثالث")
            if month.index in (2, 7, 10):
                await self.tx(book, owner, Flow.EXPENSE, "هدیه و مناسبت", _round(self.rng.uniform(1.5e6, 5e6), 100_000),
                              self.day(month, self.rng.randint(5, 25)), self.rng.choice(["هدیهٔ تولد", "هدیهٔ عروسی", "عیدی"]))

        # foreign money: a freelance client pays in tether; a subscription is paid in tether too
        for month in months:
            if month.index in (1, 4, 7, 10):
                on = self.day(month, 14)
                if on:
                    await self.tx(book, owner, Flow.INCOME, "فریلنس ارزی", 260, on, "پرداخت مشتری خارجی",
                                  currency="USDT", rate=self.usdt_rate(on))
        on = self.day(months[8], 20)
        if on:
            await self.exchange.convert(owner.id, book.id, "USDT", 400, "IRT", 400 * int(self.usdt_rate(on)), occurred_on=on,
                                        note="فروش تتر برای هزینه‌های ماه")
        for month in months[5:]:
            on = self.day(month, 3)
            if on:
                await self.tx(book, owner, Flow.EXPENSE, "اشتراک‌ها", 20, on, "اشتراک ابزار هوش مصنوعی",
                              currency="USDT", rate=self.usdt_rate(on))
        on = self.day(months[-2], 18)
        if on:
            await self.exchange.convert(owner.id, book.id, "IRT", 9_450_000, "USDT", 35, occurred_on=on,
                                        note="خرید تتر")

        # budgets
        budgets = BudgetService(self.session)
        for kind, target, amount in [
            (BudgetKind.FLOW, "expense", 52_000_000), (BudgetKind.CATEGORY, "رستوران و کافه", 6_000_000),
            (BudgetKind.CATEGORY, "حمل‌ونقل", 3_500_000), (BudgetKind.CATEGORY, "خرید خانه", 12_000_000),
            (BudgetKind.CATEGORY, "تفریح و سینما", 2_500_000),
        ]:
            await budgets.set_budget(book.id, owner.id, kind, target, amount)

        # loans: a phone on instalments (still being paid) and a car bought on a loan
        loans = LoanService(self.session)
        phone = await loans.create(book.id, owner.id, "قسط گوشی", 4_500_000, 12, months[-5].start + timedelta(days=4))
        for month in months[-5:]:
            on = self.day(month, 5)
            if on:
                await loans.record_payment(book.id, owner.id, phone.id, on=on)
        capital = CapitalService(self.session)
        car_loan = await loans.create(book.id, owner.id, "وام خودرو", 9_500_000, 48, months[-4].start + timedelta(days=9))
        car = await capital.buy_asset(
            book.id, owner.id, "پژو ۲۰۶ تیپ ۵", AssetKind.OTHER, 520_000_000, months[-4].start + timedelta(days=2),
            down_payment=150_000_000, loan_id=car_loan.id, note="خرید اقساطی",
        )
        for month in months[-3:]:
            on = self.day(month, 10)
            if on:
                await loans.record_payment(book.id, owner.id, car_loan.id, on=on)

        # gold held as a purchase, a few written-down holdings, a rotating fund, a note
        await capital.buy_asset(book.id, owner.id, "", AssetKind.GOLD, 118_000_000, months[-9].start + timedelta(days=11),
                                quantity=5, instrument="gold18", note="خرید از بازار")
        portfolio = PortfolioService(self.session)
        await portfolio.add_holding(book.id, owner.id, "USDT", 400, cost=84_000_000, acquired_on=months[-8].start + timedelta(days=6))
        await portfolio.add_holding(book.id, owner.id, "coin_quarter", 4, cost=290_000_000, acquired_on=months[-6].start + timedelta(days=3))
        await portfolio.add_holding(book.id, owner.id, "other", 1, label="سهام بانک", unit_price=26_000_000, cost=21_000_000,
                                    acquired_on=months[-10].start + timedelta(days=8))
        fund = await capital.create_fund(book.id, owner.id, "صندوق خانوادگی", 5_000_000, 12, 60_000_000,
                                         months[-7].start + timedelta(days=5), turn_month=9)
        for month in months[-7:]:
            on = self.day(month, 6)
            if on:
                await capital.contribute(book.id, owner.id, fund.id, on)
        note = await portfolio.add_note(book.id, owner.id, "زمین شمال", "قطعهٔ ۳۰۰ متری برای ساخت ویلا در آینده")
        for months_back, amount, memo in [(9, 80_000_000, "بیعانه"), (8, 12_000_000, "سند و مالیات"),
                                           (5, 35_000_000, "حصارکشی"), (2, 18_000_000, "چاه آب")]:
            await portfolio.add_entry(book.id, owner.id, note.id, "spent", months[-months_back].start + timedelta(days=9), amount, memo)
        await portfolio.add_entry(book.id, owner.id, note.id, "note", months[-1].start + timedelta(days=1), None, "قیمت‌گذاری مجدد پس از ۵ سال")

        # debts
        debts = DebtService(self.session)
        await debts.create(book.id, owner.id, "علی (همکار)", Direction.OWED_TO_ME, 6_000_000, "قرض برای اجارهٔ خانه", months[-1].end + timedelta(days=20))
        brother = await debts.create(book.id, owner.id, "برادرم", Direction.OWED_TO_ME, 20_000_000, "کمک برای خرید لپ‌تاپ", None)
        await debts.settle(book.id, owner.id, brother.id, record_transaction=False, amount=8_000_000)
        await debts.create(book.id, owner.id, "حامد (دوست)", Direction.I_OWE, 3_500_000, "خرج سفر", months[-1].end + timedelta(days=9))
        await debts.create(book.id, owner.id, "فروشگاه محله", Direction.I_OWE, 1_800_000, "خرید نسیه", months[-1].end + timedelta(days=4))

        # recurring: the rent waits to be confirmed each month, the internet books itself
        recurring = RecurringService(self.session)
        rent_day = self.day(months[-1], 1) or months[-1].start
        await recurring.create(book.id, owner.id, Flow.EXPENSE, "اجارهٔ خانه", 14_000_000, Period.MONTHLY,
                               rent_day, description="اجارهٔ ماهانه", mode=Mode.ASK, first_booked=True)
        await recurring.create(book.id, owner.id, Flow.EXPENSE, "اشتراک‌ها", 350_000, Period.MONTHLY,
                               rent_day + timedelta(days=2), description="اشتراک ماهانه", mode=Mode.AUTO, first_booked=True)
        await recurring.create(book.id, owner.id, Flow.INCOME, "حقوق", 43_500_000, Period.MONTHLY,
                               rent_day, description="حقوق ماهانه", mode=Mode.ASK, first_booked=True)

    async def shop(self, owner: User) -> None:
        book = await self.make_book(owner, "فروشگاه لوازم دیجیتال", BookType.BUSINESS)
        months = jalali_months(self.today)
        await self.exchange.set_enabled(owner.id, book.id, "USDT", True)
        await self.exchange.set_enabled(owner.id, book.id, "AED", True)

        await self.spread(book, owner, months, Flow.INCOME, [
            ("فروش حضوری", [8, 10], 6_000_000, 38_000_000, ["فروش روزانهٔ مغازه", "فروش لوازم جانبی", "فروش موبایل"], 0.02),
            ("فروش آنلاین", [3, 4], 4_000_000, 26_000_000, ["سفارش‌های اینستاگرام", "سفارش‌های سایت"], 0.03),
            ("خدمات و تعمیر", [2, 3], 1_200_000, 6_500_000, ["تعمیر موبایل", "تعویض گلس و قاب"], 0.0),
        ])
        await self.spread(book, owner, months, Flow.EXPENSE, [
            ("خرید کالا", [1, 2], 50_000_000, 110_000_000, ["خرید از عمده‌فروش", "سفارش شارژر و کابل", "خرید گوشی"], 0.012),
            ("بسته‌بندی و ارسال", [3, 4], 600_000, 2_800_000, ["پست پیشتاز", "تیپاکس", "کارتن و نوار چسب"], 0.0),
            ("تبلیغات", 2, 3_000_000, 9_000_000, ["تبلیغ اینستاگرام", "کلیکی گوگل"], 0.01),
            ("قبوض و شارژ", 2, 700_000, 2_400_000, ["برق مغازه", "اینترنت", "شارژ ساختمان"], 0.0),
            ("حقوق کارکنان", 2, 17_000_000, 19_500_000, ["حقوق فروشنده", "حقوق تکنسین تعمیرات"], 0.012),
        ])
        for month in months:
            await self.tx(book, owner, Flow.EXPENSE, "اجارهٔ مغازه", 35_000_000, self.day(month, 1), "اجارهٔ ماهانه")
            if month.index % 3 == 2:
                await self.tx(book, owner, Flow.EXPENSE, "مالیات و عوارض", _round(self.rng.uniform(8e6, 14e6), 100_000),
                              self.day(month, 20), "مالیات فصلی")
            if month.index % 4 == 1:
                await self.tx(book, owner, Flow.EXPENSE, "تعمیرات و متفرقه", _round(self.rng.uniform(1e6, 7e6), 100_000),
                              self.day(month, self.rng.randint(5, 25)), self.rng.choice(["تعمیر کولر", "ویترین", "قفل و کلید"]))
        # imports: tether bought, then spent abroad; a deposit in dirhams
        buy_on = self.day(months[6], 4)
        if buy_on:
            await self.exchange.convert(owner.id, book.id, "IRT", 1_200 * int(self.usdt_rate(buy_on)), "USDT", 1_200,
                                        occurred_on=buy_on, note="خرید تتر برای واردات")
            for k, month in enumerate(months[6:9]):
                on = self.day(month, 12)
                if on:
                    await self.tx(book, owner, Flow.EXPENSE, "خرید کالا", 380, on, "خرید از تأمین‌کنندهٔ چینی",
                                  currency="USDT", rate=self.usdt_rate(on))
        budgets = BudgetService(self.session)
        for kind, target, amount in [
            (BudgetKind.FLOW, "expense", 520_000_000), (BudgetKind.CATEGORY, "تبلیغات", 14_000_000),
            (BudgetKind.CATEGORY, "خرید کالا", 360_000_000), (BudgetKind.CATEGORY, "بسته‌بندی و ارسال", 9_000_000),
        ]:
            await budgets.set_budget(book.id, owner.id, kind, target, amount)

        loans = LoanService(self.session)
        working = await loans.create(book.id, owner.id, "وام سرمایه در گردش", 18_000_000, 24, months[-7].start + timedelta(days=14))
        for month in months[-6:]:
            on = self.day(month, 15)
            if on:
                await loans.record_payment(book.id, owner.id, working.id, on=on)
        debts = DebtService(self.session)
        await debts.create(book.id, owner.id, "شرکت پارس‌گستر", Direction.OWED_TO_ME, 85_000_000, "فروش اقساطی لپ‌تاپ سازمانی", months[-1].end + timedelta(days=15))
        await debts.create(book.id, owner.id, "فروشگاه آقای محمدی", Direction.OWED_TO_ME, 22_000_000, "فروش عمده", months[-1].end + timedelta(days=6))
        supplier = await debts.create(book.id, owner.id, "تأمین‌کنندهٔ لوازم جانبی", Direction.I_OWE, 120_000_000, "فاکتور خرید نسیه", months[-1].end + timedelta(days=21))
        await debts.settle(book.id, owner.id, supplier.id, record_transaction=False, amount=40_000_000)
        recurring = RecurringService(self.session)
        await recurring.create(book.id, owner.id, Flow.EXPENSE, "اجارهٔ مغازه", 35_000_000, Period.MONTHLY,
                               self.day(months[-1], 1) or months[-1].start, description="اجارهٔ ماهانه", mode=Mode.ASK, first_booked=True)
        await self.extra_categories(book, owner, Flow.EXPENSE, ["بیمه", "حمل بار", "آموزش کارکنان"])
        await self.extra_categories(book, owner, Flow.INCOME, ["فروش اقساطی", "کمیسیون"])

    async def studio(self, owner: User) -> None:
        book = await self.make_book(owner, "استودیو طراحی نیکان", BookType.TEAM)
        months = jalali_months(self.today)
        sara = await self.add_member(book, "سارا احمدی", Role.ADMIN)
        ali = await self.add_member(book, "علی رضایی", Role.ACCOUNTANT)
        maryam = await self.add_member(book, "مریم کاظمی", Role.MEMBER)
        await self.add_member(book, "محمد حسینی", Role.VIEWER)

        await self.spread(book, owner, months, Flow.INCOME, [
            ("پروژهٔ طراحی سایت", [1, 2], 30_000_000, 110_000_000, ["طراحی و توسعهٔ سایت فروشگاهی", "بازطراحی سایت شرکتی", "طراحی صفحهٔ فرود"], 0.015),
            ("طراحی هویت بصری", 1, 20_000_000, 55_000_000, ["لوگو و بروشور", "بسته هویت بصری"], 0.0),
            ("نگهداری و پشتیبانی", 2, 6_000_000, 14_000_000, ["قرارداد پشتیبانی ماهانه", "هاستینگ و به‌روزرسانی"], 0.01),
        ])
        await self.spread(book, owner, months, Flow.EXPENSE, [
            ("اجارهٔ فضای کار", 1, 30_000_000, 30_000_000, ["اجارهٔ فضای اشتراکی"], 0.0),
            ("نرم‌افزار و اشتراک", [2, 3], 1_200_000, 9_000_000, ["Figma", "Adobe", "هاست و دامنه", "ابزارهای مدیریت پروژه"], 0.0),
            ("برون‌سپاری", [1, 2], 8_000_000, 26_000_000, ["فریلنسر تصویرسازی", "برنامه‌نویس پاره‌وقت", "عکاسی"], 0.0),
            ("تجهیزات", 1, 1_500_000, 18_000_000, ["مانیتور", "هارد اکسترنال", "میز و صندلی"], 0.0),
            ("بازاریابی", 1, 3_000_000, 12_000_000, ["تبلیغات لینکدین", "نمونه‌کار و چاپ"], 0.0),
            ("اینترنت و قبوض", 1, 1_200_000, 2_600_000, ["اینترنت", "قبض"], 0.0),
        ])
        # the share rules and the treasury: from the start of the year
        payroll = PayrollService(self.session)
        start = months[0].start
        for user, percent in [(owner, 35), (sara, 25), (ali, 20), (maryam, 10)]:
            await payroll.set_share(book.id, owner.id, user.id, ShareBasis.PERCENT, percent, effective_from=start)
        treasury = TreasuryService(self.session)
        growth = await treasury.create_fund(book.id, owner.id, "صندوق توسعه", FundKind.DEVELOPMENT)
        await treasury.add_rule(book.id, owner.id, growth.id, RuleBasis.GROSS_PERCENT, 10, effective_from=start)
        reserve = await treasury.create_fund(book.id, owner.id, "صندوق اضطراری", FundKind.EMERGENCY)
        await treasury.add_rule(book.id, owner.id, reserve.id, RuleBasis.NET_PERCENT, 5, effective_from=start)

        # every whole month so far is worked out, paid and locked; the newest one is left owing
        finished = months[:-1]
        for k, month in enumerate(finished):
            period = await payroll.open_period(owner.id, book.id, month.label, month.start, month.end)
            slips = await payroll.calculate(owner.id, period.id)
            newest = k == len(finished) - 1
            for slip in slips:
                owed = slip.net_pay
                if owed <= 0:
                    continue
                if newest and slip.user_id == maryam.id:
                    continue  # still owed: the demo shows an open payable
                await payroll.pay(owner.id, slip.id, owed, paid_on=min(month.end + timedelta(days=5), self.today))
            if not newest:
                await payroll.close_period(owner.id, period.id)
        budgets = BudgetService(self.session)
        for kind, target, amount in [(BudgetKind.FLOW, "expense", 90_000_000), (BudgetKind.CATEGORY, "برون‌سپاری", 30_000_000),
                                     (BudgetKind.CATEGORY, "نرم‌افزار و اشتراک", 10_000_000)]:
            await budgets.set_budget(book.id, owner.id, kind, target, amount)
        debts = DebtService(self.session)
        await debts.create(book.id, owner.id, "شرکت آسمان‌پرداز", Direction.OWED_TO_ME, 64_000_000, "تسویهٔ پروژهٔ سایت", months[-1].end + timedelta(days=12))
        await debts.create(book.id, owner.id, "طراح مهمان (کاوه)", Direction.I_OWE, 14_000_000, "مانده از برون‌سپاری", months[-1].end + timedelta(days=7))
        await self.extra_categories(book, owner, Flow.EXPENSE, ["آموزش تیم", "پذیرایی", "سفر کاری"])
        await self.extra_categories(book, owner, Flow.INCOME, ["مشاوره", "فروش قالب"])

    async def company(self, owner: User) -> None:
        book = await self.make_book(owner, "شرکت بازرگانی آریا", BookType.ORGANIZATION, calendar="gregorian")
        months = gregorian_months(self.today)
        for name, role in [("نرگس صادقی", Role.ADMIN), ("حسین موسوی", Role.ACCOUNTANT), ("زهرا نیک‌نام", Role.ACCOUNTANT),
                           ("رضا کریمی", Role.MEMBER), ("لیلا امینی", Role.MEMBER), ("امیر فرهادی", Role.VIEWER)]:
            await self.add_member(book, name, role)
        await self.exchange.set_enabled(owner.id, book.id, "USDT", True)
        await self.exchange.set_enabled(owner.id, book.id, "AED", True)
        await self.spread(book, owner, months, Flow.INCOME, [
            ("فروش عمده", [3, 4], 55_000_000, 260_000_000, ["فروش به عمده‌فروشان", "قرارداد تأمین سالانه", "سفارش شرکتی"], 0.02),
            ("خدمات مشاوره‌ای", 1, 12_000_000, 40_000_000, ["مشاورهٔ بازرگانی", "ترخیص و حمل"], 0.0),
            ("درآمد متفرقه", 1, 3_000_000, 14_000_000, ["فروش ضایعات", "کارمزد نمایندگی"], 0.0),
        ])
        await self.spread(book, owner, months, Flow.EXPENSE, [
            ("خرید کالا", [1, 2], 70_000_000, 190_000_000, ["خرید از تولیدکننده", "واردات محموله", "خرید مواد اولیه"], 0.015),
            ("حقوق و دستمزد", 2, 52_000_000, 95_000_000, ["حقوق کارکنان اداری", "حقوق انبار و فروش"], 0.01),
            ("اجارهٔ دفتر و انبار", 2, 26_000_000, 38_000_000, ["اجارهٔ دفتر مرکزی", "اجارهٔ انبار"], 0.0),
            ("حمل و گمرک", [2, 3], 4_000_000, 22_000_000, ["کرایهٔ حمل", "ترخیص گمرکی", "بیمهٔ محموله"], 0.0),
            ("بازاریابی", 1, 5_000_000, 18_000_000, ["نمایشگاه", "تبلیغات", "کاتالوگ"], 0.0),
            ("قبوض و اداری", [2, 3], 2_000_000, 8_000_000, ["قبوض", "لوازم اداری", "پذیرایی"], 0.0),
        ])
        for month in months:
            if month.index % 3 == 2:
                await self.tx(book, owner, Flow.EXPENSE, "مالیات و بیمه", _round(self.rng.uniform(20e6, 40e6), 100_000),
                              self.day(month, 20), "مالیات و حق بیمهٔ فصلی")
        on = self.day(months[5], 6)
        if on:
            await self.exchange.convert(owner.id, book.id, "IRT", 2_000 * 73_500, "AED", 2_000, occurred_on=on,
                                        note="خرید درهم برای تسویهٔ واردات")
            await self.tx(book, owner, Flow.EXPENSE, "خرید کالا", 1_700, self.day(months[6], 5), "تسویهٔ محمولهٔ دبی",
                          currency="AED", rate=Decimal("73500"))
        budgets = BudgetService(self.session)
        for kind, target, amount in [(BudgetKind.FLOW, "expense", 420_000_000), (BudgetKind.CATEGORY, "حمل و گمرک", 38_000_000),
                                     (BudgetKind.CATEGORY, "بازاریابی", 24_000_000), (BudgetKind.CATEGORY, "قبوض و اداری", 14_000_000)]:
            await budgets.set_budget(book.id, owner.id, kind, target, amount)
        loans = LoanService(self.session)
        facility = await loans.create(book.id, owner.id, "تسهیلات بانکی", 22_000_000, 36, months[-8].start + timedelta(days=9))
        for month in months[-7:]:
            on = self.day(month, 10)
            if on:
                await loans.record_payment(book.id, owner.id, facility.id, on=on)
        debts = DebtService(self.session)
        await debts.create(book.id, owner.id, "شرکت کیان‌تجارت", Direction.OWED_TO_ME, 150_000_000, "فروش عمدهٔ فصل", months[-1].end + timedelta(days=25))
        await debts.create(book.id, owner.id, "گمرک و حمل‌ونقل پارسیان", Direction.I_OWE, 42_000_000, "کرایهٔ حمل معوق", months[-1].end + timedelta(days=10))
        recurring = RecurringService(self.session)
        await recurring.create(book.id, owner.id, Flow.EXPENSE, "اجارهٔ دفتر و انبار", 34_000_000, Period.MONTHLY,
                               self.day(months[-1], 1) or months[-1].start, description="اجارهٔ ماهانه", mode=Mode.AUTO, first_booked=True)
        await self.extra_categories(book, owner, Flow.EXPENSE, ["آموزش کارکنان", "سفر کاری", "تعمیر و نگهداری"])


def jalali_now():
    from ...shared.security import utcnow

    return utcnow()


async def seed_demo(session: AsyncSession, today: Optional[date] = None) -> Tuple[User, int]:
    """Make the demo account with its four books. Returns the owner and how many ledger rows were written."""
    today = today or jalali.today_in(jalali.DEFAULT_TIMEZONE)
    owner = User(display_name=DEMO_NAME, username=DEMO_USERNAME, is_guest=True)
    session.add(owner)
    await session.flush()
    seeder = Seeder(session, today)
    await seeder.personal(owner)
    await seeder.shop(owner)
    await seeder.studio(owner)
    await seeder.company(owner)
    return owner, seeder.rows


async def _existing(session: AsyncSession) -> Optional[User]:
    return (
        await session.execute(select(User).where(User.username == DEMO_USERNAME))
    ).scalar_one_or_none()


def _age(user: User) -> timedelta:
    made = user.created_at
    if made.tzinfo is None:  # sqlite hands the time back without its zone
        made = made.replace(tzinfo=timezone.utc)
    return utcnow() - made


async def ensure_demo(session: AsyncSession, today: Optional[date] = None) -> User:
    """The one shared demo account: made if it is not there, renewed if it is old, otherwise as it is.

    Two first visits at once both try to make it; the second waits on the unique name until the first
    has committed, finds the account when it gets there, and signs in to that one.
    """
    user = await _existing(session)
    if user is not None and _age(user) > timedelta(days=DEMO_LIFETIME_DAYS):
        await IdentityService(session).delete_account(user.id, renewing_demo=True)
        user = None
    if user is not None:
        return user
    try:
        async with session.begin_nested():
            owner, _ = await seed_demo(session, today)
        return owner
    except IntegrityError:
        found = await _existing(session)
        if found is None:
            raise
        return found
