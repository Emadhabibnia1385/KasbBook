"""Writes the activity log as a side effect of the change itself.

A listener on every session's flush looks at what is being inserted, changed or deleted and, for the models
people work with, adds a line to `activity_events` in the same transaction. So the log cannot miss a change
(no route has to remember), cannot outlive one that was rolled back, and covers the panel, the API and the
bot alike, because all three change data through the same models.

Who did it comes from a context variable the entry points set: the API dependency (the person, or the API
key that stands for them) and the bot's conversation. Nothing set means nobody asked: a schedule or a sync of
the system's own. Only already-loaded attributes are read, because a flush runs where nothing may be awaited.
"""

from __future__ import annotations

import contextlib
import contextvars
import enum
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .models import VIA_API, VIA_BOT, VIA_SYSTEM, VIA_WEB, ActivityEvent


@dataclass(frozen=True)
class Actor:
    user_id: Optional[uuid.UUID]
    via: str


_actor: contextvars.ContextVar[Optional[Actor]] = contextvars.ContextVar("activity_actor", default=None)
_paused: contextvars.ContextVar[bool] = contextvars.ContextVar("activity_paused", default=False)


def set_actor(user_id: Optional[uuid.UUID], via: str) -> contextvars.Token:
    return _actor.set(Actor(user_id, via))


def clear_actor(token: Optional[contextvars.Token] = None) -> None:
    if token is not None:
        _actor.reset(token)
    else:
        _actor.set(None)


@contextlib.contextmanager
def paused() -> Iterator[None]:
    """Nothing is logged inside: for a seeder that writes a thousand made-up rows."""
    token = _paused.set(True)
    try:
        yield
    finally:
        _paused.reset(token)


# ------------------------------------------------------------------ what each model is called
# model class name -> (category, what it is called, the field that names it)
TRACKED: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {
    "Transaction": ("transactions", "تراکنش", ("category",)),
    "Category": ("categories", "دسته", ("name",)),
    "Budget": ("budgets", "بودجه", ("target",)),
    "Debt": ("debts", "بدهی یا طلب", ("person",)),
    "Loan": ("loans", "وام یا قسط", ("title",)),
    "LoanPayment": ("loans", "پرداخت قسط", ()),
    "RecurringRule": ("recurring", "تراکنش تکرارشونده", ("category",)),
    "Asset": ("capital", "دارایی", ("name",)),
    "Fund": ("capital", "صندوق قرضه‌الحسنه", ("name",)),
    "Holding": ("portfolio", "سرمایه", ("label", "instrument")),
    "FinancialNote": ("portfolio", "یادداشت مالی", ("title",)),
    "NoteEntry": ("portfolio", "ردیف یادداشت", ()),
    "CurrencyConversion": ("wallet", "تبدیل ارز", ()),
    "BookCurrency": ("wallet", "ارز دفتر", ("code",)),
    "Payment": ("payroll", "پرداخت حقوق", ()),
    "Adjustment": ("payroll", "تعدیل فیش", ("reason",)),
    "ShareRule": ("payroll", "سهم عضو", ()),
    "FinancialPeriod": ("payroll", "دورهٔ مالی", ("label",)),
    "TreasuryFund": ("treasury", "صندوق", ()),
    "TreasuryRule": ("treasury", "قاعدهٔ صندوق", ("category",)),
    "Membership": ("members", "عضو دفتر", ()),
    "Book": ("books", "دفتر", ("name",)),
    "ApiKey": ("account", "کلید API", ("name", "label")),
}

CATEGORY_LABELS = {
    "transactions": "تراکنش‌ها",
    "categories": "دسته‌ها",
    "budgets": "بودجه",
    "debts": "بدهی و طلب",
    "loans": "وام و قسط",
    "recurring": "تکرارشونده‌ها",
    "capital": "سرمایه و دارایی",
    "portfolio": "داشته‌ها و یادداشت‌ها",
    "wallet": "کیف پول و ارز",
    "payroll": "حقوق و فیش",
    "treasury": "صندوق‌ها",
    "members": "اعضا",
    "books": "دفترها",
    "account": "حساب و ورود",
}

VERBS = {"created": "افزودن", "updated": "ویرایش", "deleted": "حذف"}

# Columns that change as a consequence, not because a person chose to.
QUIET = {
    "updated_at", "created_at", "last_edited_at", "last_edited_by_id", "converted_amount", "base_value",
    "rate_at", "rate_source", "rate_mode", "category_id", "locked_at", "paid_amount", "paid_months",
    "settled_at", "owed", "claim", "next_run_on", "last_run_on", "hashed_key", "last_used_at",
}

FIELD_LABELS = {
    "amount": "مبلغ", "original_amount": "مبلغ", "cost": "قیمت خرید", "quantity": "مقدار",
    "category": "دسته", "name": "نام", "title": "عنوان", "description": "توضیح", "note": "توضیح",
    "memo": "توضیح", "occurred_on": "تاریخ", "due_on": "سررسید", "status": "وضعیت",
    "is_active": "فعال بودن", "role": "نقش", "label": "نام", "person": "نام", "flow": "نوع",
    "original_currency": "ارز", "currency": "ارز", "conversion_rate": "نرخ", "starts_on": "شروع",
    "ends_on": "پایان", "value": "مقدار", "basis": "مبنا", "period": "دوره", "mode": "حالت",
    "target": "هدف", "instrument": "چه چیزی", "sold_on": "تاریخ فروش", "sold_for": "قیمت فروش",
    "text": "متن", "unit_price": "قیمت واحد", "acquired_on": "تاریخ خرید", "installment_amount": "مبلغ قسط",
    "kind": "نوع", "net_pay": "خالص پرداخت", "base_currency": "ارز پایه", "calendar": "تقویم",
    "cost_policy": "سیاست هزینه", "reason": "دلیل", "type": "نوع", "direction": "جهت",
}


def _loaded(obj: Any, name: str) -> Any:
    """The attribute if it is already in memory; never a database round trip."""
    return obj.__dict__.get(name)


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, enum.Enum) else value


def _money(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except Exception:  # noqa: BLE001 - not a number: show it as it is
        return str(value)
    text = f"{number:,.4f}".rstrip("0").rstrip(".")
    return text


def _currency_name(code: Optional[str]) -> str:
    if not code:
        return ""
    from ..exchange.models import CURRENCY_NAMES

    return CURRENCY_NAMES.get(code, code)


def _amount_text(obj: Any) -> str:
    for amount_field, currency_field in (
        ("original_amount", "original_currency"), ("amount", "currency"), ("installment_amount", None),
        ("cost", None), ("from_amount", "from_currency"), ("value", None),
    ):
        amount = _loaded(obj, amount_field)
        if amount in (None, ""):
            continue
        currency = _loaded(obj, currency_field) if currency_field else None
        return f"{_money(amount)} {_currency_name(currency)}".strip()
    return ""


def _name_of(obj: Any, fields: Tuple[str, ...]) -> str:
    for field in fields:
        value = _loaded(obj, field)
        if value:
            return str(_plain(value))[:60]
    return ""


def _changes(obj: Any) -> List[str]:
    state = inspect(obj)
    names: List[str] = []
    for attr in state.mapper.column_attrs:
        if attr.key in QUIET:
            continue
        if state.attrs[attr.key].history.has_changes():
            label = FIELD_LABELS.get(attr.key, attr.key)
            if label not in names:
                names.append(label)
    return names


def _book_of(obj: Any) -> Optional[uuid.UUID]:
    if obj.__class__.__name__ == "Book":
        return _loaded(obj, "id")
    return _loaded(obj, "book_id")


def _summary(kind: str, obj: Any, verb: str, changed: List[str]) -> str:
    category, noun, name_fields = TRACKED[kind]
    name = _name_of(obj, name_fields)
    amount = _amount_text(obj)
    if kind == "Transaction":
        flow = _plain(_loaded(obj, "flow"))
        what = "درآمد" if flow == "income" else "هزینه"
        head = {"created": f"ثبت {what}", "updated": f"ویرایش {what}", "deleted": f"حذف {what}"}[verb]
        parts = [head, amount, f"— {name}" if name else ""]
        description = _loaded(obj, "description")
        if description and verb != "updated":
            parts.append(f"({str(description)[:50]})")
    else:
        parts = [f"{VERBS[verb]} {noun}", f"«{name}»" if name else "", amount]
    if verb == "updated" and changed:
        parts.append("(" + "، ".join(changed) + ")")
    return " ".join(part for part in parts if part)


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    if _paused.get():
        return
    actor = _actor.get()
    user_id = actor.user_id if actor else None
    via = actor.via if actor else VIA_SYSTEM

    pending: List[Tuple[Any, str]] = []
    pending.extend((obj, "created") for obj in session.new)
    pending.extend(
        (obj, "updated") for obj in session.dirty if session.is_modified(obj, include_collections=False)
    )
    pending.extend((obj, "deleted") for obj in session.deleted)

    for obj, verb in pending:
        kind = obj.__class__.__name__
        if kind not in TRACKED:
            continue
        changed: List[str] = []
        if verb == "updated":
            changed = _changes(obj)
            if not changed:
                continue
        category, _noun, _fields = TRACKED[kind]
        session.add(
            ActivityEvent(
                user_id=user_id,
                via=via,
                book_id=_book_of(obj),
                category=category,
                action=f"{kind[0].lower()}{kind[1:]}.{verb}",
                summary=_summary(kind, obj, verb, changed),
                entity_id=_loaded(obj, "id"),
            )
        )


_installed = False


def install() -> None:
    global _installed
    if not _installed:
        event.listen(Session, "before_flush", _before_flush)
        _installed = True


def record(
    session: Session,
    *,
    category: str,
    action: str,
    summary: str,
    user_id: Optional[uuid.UUID] = None,
    via: str = VIA_WEB,
    book_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
) -> None:
    """A line that is not the side effect of a model change (signing in, signing out)."""
    if _paused.get():
        return
    session.add(
        ActivityEvent(
            user_id=user_id, via=via, book_id=book_id, category=category, action=action,
            summary=summary, entity_id=entity_id,
        )
    )


__all__ = [
    "Actor", "CATEGORY_LABELS", "VIA_API", "VIA_BOT", "VIA_SYSTEM", "VIA_WEB", "clear_actor", "install",
    "paused", "record", "set_actor",
]
