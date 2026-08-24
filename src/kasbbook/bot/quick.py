"""Reading a transaction out of one typed line.

"فروش 250000" should be a recorded transaction, not the start of a five-tap
menu. This parses the line; it never guesses. If the line is not clearly a
transaction, it says so rather than recording money that never moved.

Ported from the first generation, where the shape was learned from use. The
change here is that the direction cannot be inferred from a category alone,
because a book now has to be chosen too — so an ambiguous line asks once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from ..shared.parsing import parse_amount, parse_date


@dataclass(frozen=True)
class QuickEntry:
    category: str
    amount: Decimal
    description: Optional[str] = None
    on: Optional[date] = None


def parse(text: str, today: Optional[date] = None) -> Optional[QuickEntry]:
    """
    Read "<category> <amount> [note]".

    An optional date may lead. The amount splits the line: what comes before it
    is the category, so multi-word names work; what comes after is the note. If
    the amount leads instead, the next single word is the category.
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None

    tokens = raw.split()
    if len(tokens) < 2:
        return None

    on = None
    if len(tokens) > 2:
        leading = parse_date(tokens[0], today)
        if leading is not None:
            on = leading
            tokens = tokens[1:]

    if len(tokens) < 2:
        return None

    index, amount, width = -1, None, 1
    for position in range(len(tokens)):
        # Two-token forms like "250 هزار" have to be tried before the single one.
        if position + 1 < len(tokens):
            pair = parse_amount(tokens[position] + tokens[position + 1])
            if pair is not None and parse_amount(tokens[position + 1]) is None:
                index, amount, width = position, pair, 2
                break

        single = parse_amount(tokens[position])
        if single is not None:
            index, amount, width = position, single, 1
            break

    if amount is None or index < 0:
        return None

    before = tokens[:index]
    after = tokens[index + width:]

    if before:
        category = " ".join(before)
        note = " ".join(after) or None
    else:
        if not after:
            return None
        category = after[0]
        note = " ".join(after[1:]) or None

    category = category.strip()
    if not category:
        return None

    return QuickEntry(category=category, amount=amount, description=note, on=on)
