"""Money that stays exact.

SQLAlchemy's `Numeric` degrades to a float on SQLite, which silently loses cents
and makes a double-entry ledger fail to balance for reasons no one can find.
`Money` sidesteps that: NUMERIC on PostgreSQL, TEXT on SQLite, `Decimal` in
Python on both. No code above this layer ever sees a float.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional, Union

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator

# Four places is enough for a rial and for a crypto rate quoted per unit.
SCALE = Decimal("0.0001")
ZERO = Decimal("0")

Amount = Union[Decimal, int, str]


def to_decimal(value: Optional[Amount]) -> Decimal:
    """Accept whatever a caller has and return an exact Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Never construct a Decimal from a float directly — Decimal(0.1) is
        # 0.1000000000000000055511151231257827. Go through the string form.
        return Decimal(repr(value))
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"not a valid amount: {value!r}") from exc


def quantize(value: Optional[Amount]) -> Decimal:
    """Round to the stored scale, the way an accountant would."""
    return to_decimal(value).quantize(SCALE, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    """Exact decimal storage on every engine we support."""

    impl = Numeric
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Numeric(28, 4, asdecimal=True))
        # SQLite has no real decimal type; text round-trips without loss.
        return dialect.type_descriptor(String(40))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        exact = quantize(value)
        if dialect.name == "postgresql":
            return exact
        # Fixed width so lexical ordering matches numeric ordering for
        # non-negative values, and negatives stay readable.
        return format(exact, "f")

    def process_result_value(self, value: Any, dialect) -> Optional[Decimal]:
        if value is None:
            return None
        return quantize(value)
