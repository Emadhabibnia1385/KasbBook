"""Reading a transaction out of one typed line.

"فروش 250000" should be a recorded transaction, not the start of a five-tap
menu. This parses the line; it never guesses. If the line is not clearly a
transaction, it says so rather than recording money that never moved.

Ported from the first generation, where the shape was learned from use. This
module reads the line and only the line: a direction is not written in it, and
whether the book's own categories already settle one is a question for
`features/transactions.py`, which has the book to answer it with.

"Never guess" has a second half: a line that *has* numbers but no single number
that is plainly the amount is not unreadable, it is unclear — and it is worth
telling the person which numbers were seen, because "۲ عدد نان ۲۰۰۰۰" recorded
as 2 is a wrong ledger that looks right.

Being unclear is not a dead end either. A refusal carries the readings it
refused to choose between, and `resolve` takes the one the person pointed at —
so the commonest refusals cost a tap instead of a retyped line. The pointing is
still theirs: nothing here picks a reading on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from ..shared.parsing import _UNITS, parse_amount, parse_date, to_ascii_digits


@dataclass(frozen=True)
class QuickEntry:
    category: str
    amount: Decimal
    description: Optional[str] = None
    on: Optional[date] = None


@dataclass(frozen=True)
class Unclear:
    """A line with numbers in it but no amount that can be trusted.

    `reason` is one of: several, grouping, dots, rial, zero, compound,
    nocategory, negative.
    `numbers` are the figures as the person typed them, for the question.
    `amounts` are the readings that question is between, as money — the same
    ones it reads out, and in the same order. They were computed and thrown
    away, so every refusal cost a retyped line; a screen can offer one button
    per reading instead. Empty when the way out is not a choice among readings:
    a rial amount needs a different figure, not a different reading of this one.
    """

    reason: str
    numbers: Tuple[str, ...] = ()
    amounts: Tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        # Frozen, so set through object: figures are echoed in one digit style.
        object.__setattr__(self, "numbers", tuple(to_ascii_digits(n) for n in self.numbers))


# Magnitudes that may follow a number as a separate word. Derived from the one
# table `parse_amount` reads, never typed out again: while this held only the
# spelled-out words, «250ک» was 250,000 and «250 ک» was 250 with «ک» filed as
# the note — a silent thousand-fold undercount on the one path that records
# without a confirmation step. A space cannot be allowed to change what a line
# means, so whatever the parser accepts glued to the digits it accepts beside
# them.
_UNIT_WORDS = dict(_UNITS)

# A number followed by one of these counts things; it does not price them.
# "۲ عدد نان ۲۰۰۰۰" is two loaves for 20,000, and the 2 is not the amount.
_QUANTITY_WORDS = frozenset({
    "عدد", "تا", "کیلو", "کیلوگرم", "گرم", "لیتر", "بسته", "جعبه", "کارتن",
    "بطری", "قوطی", "دست", "جفت", "متر", "شاخه", "پاکت", "کیسه", "نفر",
    "ساعت", "روز", "ماه", "هفته", "جلسه", "بار",
})

# The book's money is toman, so the word adds nothing and is not a note.
_TOMAN_WORDS = frozenset({"تومان", "تومن"})

# Every dash a keyboard offers for a minus. All of them mean the same refusal.
_MINUS_SIGNS = ("-", "−", "–", "—")

_GROUPED = re.compile(r"\d{1,3}([,،٬]\d{3})+(\.\d+)?")
_DOT_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")
_NUMBER_BODY = re.compile(r"([\d.,٫،٬‌]+)(\D*)")


@dataclass(frozen=True)
class _Segment:
    value: Decimal
    unit: Decimal       # 1 for a bare number, 1000 for "هزار" or "ک", ...
    start: int
    width: int
    typed: str


def _without_toman(token: str) -> Optional[Decimal]:
    """«250هزارتومان», where the magnitude and the word for the money run together.

    `parse_amount` reads a magnitude only at the very end of a token, so the
    word hid it and the whole line came back with no number in it at all —
    «مبلغی در این پیام ندیدم» about a line that is nothing but an amount. The
    book counts in toman, so the word carries nothing. The spaced form («250
    هزار تومان») already worked, and a space may not change what a line means.
    """
    for word in _TOMAN_WORDS:
        if token.endswith(word) and len(token) > len(word):
            return parse_amount(token[: -len(word)])
    return None


def _segment(tokens: List[str], index: int) -> Optional[_Segment]:
    """One number at `index`, with its magnitude word if it has one."""
    token = tokens[index]
    value = parse_amount(token)
    if value is None:
        value = _without_toman(token)
    width = 1
    if value is not None:
        typed = token
    else:
        return None

    # "250 هزار": the unit is a separate word. Only when the number itself
    # carries no unit, or "۲۵۰ک هزار" would be read as a million.
    follower = tokens[index + 1] if index + 1 < len(tokens) else ""
    # Lowered for the lookup only: `parse_amount` is case-insensitive, so "250 K"
    # means what "250 k" means, while `typed` keeps what the person wrote.
    unit_key = follower.lower()
    if unit_key in _UNIT_WORDS and re.fullmatch(r"[\d.,٫،٬]+", to_ascii_digits(token)):
        joined = parse_amount(token + follower)
        if joined is not None:
            value, width, typed = joined, 2, f"{token} {follower}"

    body = _NUMBER_BODY.fullmatch(to_ascii_digits(typed.split(" ")[0]))
    base = parse_amount(body.group(1)) if body else None
    unit = Decimal(1)
    if width == 2:
        unit = _UNIT_WORDS[unit_key]
    elif base:
        unit = value / base
    return _Segment(value, unit, index, width, typed)


def _split_figure(typed: str) -> Optional[Tuple[str, str]]:
    """A figure as (digits, magnitude), with the word for the money dropped.

    «تومان» is not a magnitude, and leaving it on the end would let
    «250.000تومان» pass the two-way-reading check that «250.000» is caught by —
    silently reading a quarter of a toman where 250,000 was meant.
    """
    body = _NUMBER_BODY.fullmatch(to_ascii_digits(typed.split(" ")[0]))
    if not body:
        return None
    suffix = body.group(2)
    for word in _TOMAN_WORDS:
        if suffix.endswith(word):
            suffix = suffix[: -len(word)]
            break
    return body.group(1).replace("‌", ""), suffix


def _without_money_word(typed: str) -> str:
    """What was typed, less a «تومان» glued onto the end of the figure.

    The echo is not only read: `unclear_reason` computes both readings of a
    dotted figure *from* it, and a word glued to the digits is not something
    `Decimal` can read. It is dropped from the echo for the same reason it is
    dropped from the amount — the book counts in toman, so it says nothing.
    """
    for word in _TOMAN_WORDS:
        if typed.endswith(word) and len(typed) > len(word):
            return typed[: -len(word)]
    return typed


def _dot_readings(typed: str) -> Tuple[Decimal, ...]:
    """The amounts a dotted figure could stand for, in the order it is asked about.

    Exactly the readings `_UNCLEAR`'s question reads out — «250 است یا
    250,000؟» — and no others, so a button never offers a figure the sentence
    beside it did not name. More than one dot has only the grouped reading.
    """
    split = _split_figure(typed)
    if split is None:
        return ()
    number, magnitude = split
    plain = parse_amount(number + magnitude) if number.count(".") == 1 else None
    grouped = parse_amount(number.replace(".", "") + magnitude)
    return tuple(value for value in (plain, grouped) if value is not None and value > 0)


def _malformed_digits(typed: str) -> Optional[str]:
    """A separator pattern whose meaning cannot be told from another one."""
    split = _split_figure(typed)
    if split is None:
        return None
    number, suffix = split
    if re.search(r"[,،٬]", number) and not _GROUPED.fullmatch(number):
        # "1,5" is one and a half to some people and fifteen to the parser.
        return "grouping"
    if not suffix and _DOT_THOUSANDS.fullmatch(number):
        # "250.000" is two hundred and fifty thousand in Persian typing and a
        # quarter in the parser.
        return "dots"
    return None


def _amount_at(tokens: List[str], index: int):
    """The amount starting at `index`, compound forms included.

    Returns (value, width, typed) or an Unclear. "۳۰ هزار و ۵۰۰" is 30,500 and
    "۲ میلیون و ۳۰۰ هزار" is 2,300,000: each part after "و" has to be smaller
    than the unit before it, or the line is not a sum and nobody should guess.
    """
    first = _segment(tokens, index)
    if first is None:
        return None

    total, width, typed, unit = first.value, first.width, first.typed, first.unit
    while unit > 1 and index + width + 1 < len(tokens) and tokens[index + width] == "و":
        nxt = _segment(tokens, index + width + 1)
        if nxt is None:
            break
        if nxt.value >= unit:
            return Unclear("compound", (typed, nxt.typed))
        if nxt.unit == 1 and unit > 1000:
            # "۲ میلیون و ۵۰۰": 2,000,500 written, 2,500,000 meant. Both are
            # common, so it is asked rather than chosen.
            return Unclear("compound", (typed, nxt.typed))
        total += nxt.value
        width += 1 + nxt.width
        typed = f"{typed} و {nxt.typed}"
        unit = nxt.unit
    return total, width, typed


def read_amount(text: str) -> Union[Decimal, Unclear, None]:
    """An amount typed on its own, in the same forms a quick line accepts.

    «۳۰ هزار و ۵۰۰» and «250 هزار تومان» are understood; anything left over
    after the amount means the text is not just an amount (None); a form that
    could be read two ways comes back as Unclear. Zero is returned as zero:
    whether that is acceptable is the caller's question.
    """
    tokens = (text or "").split()
    if not tokens:
        return None
    got = _amount_at(tokens, 0)
    if got is None or isinstance(got, Unclear):
        return got
    value, width, typed = got
    rest = tokens[width:]
    if rest and rest[0] in _TOMAN_WORDS:
        rest = rest[1:]
    elif rest and rest[0] == "ریال":
        return Unclear("rial", (typed,))
    if rest:
        return None
    problem = _malformed_digits(typed)
    if problem:
        figure = _without_money_word(typed)
        return Unclear(problem, (figure,), _dot_readings(figure) if problem == "dots" else ())
    return value


def _lonely_amount(tokens: List[str]) -> Optional[Unclear]:
    """An amount with nothing to spend it on: ask for the category, not for an amount.

    «250000» on its own used to answer "I saw no amount in this message", which
    is the one thing the line certainly does have. Anything that is not an
    amount stays unreadable, so ordinary chat is not answered with a nag.
    """
    if len(tokens) != 1:
        return None
    value = parse_amount(tokens[0])
    if value is None:
        return None
    return Unclear("nocategory", (tokens[0],))


def _negative(tokens: List[str]) -> Optional[str]:
    """A token that is an amount with a minus sign in front of it, or None.

    `parse_amount` reads no sign, so «فروش -250000» found no number at all and
    was answered with "I saw no amount in this message" — about a line whose
    amount is the only thing it certainly has. `features/base.read_amount`
    already had the sentence for this; the one-line path never reached it
    because it reads through `read`, not through that.
    """
    for token in tokens:
        digits = to_ascii_digits(token)
        if digits[:1] in _MINUS_SIGNS and parse_amount(digits[1:]) is not None:
            return token
    return None


def _dot_grouped(tokens: List[str]) -> Optional[str]:
    """A token that is only readable as dot-grouped thousands, or None.

    `parse_amount` refuses two dots outright, so «1.500.000» — the commonest
    Persian typing style — found no number at all and came back as unreadable,
    the one refusal that teaches nothing. It is asked about rather than read,
    for the same reason rials are: picking a reading silently is a guess.
    """
    for token in tokens:
        digits = to_ascii_digits(token)
        if _DOT_THOUSANDS.fullmatch(digits) and digits.count(".") > 1:
            return token
    return None


def read(text: str, today: Optional[date] = None, *,
         prefer: Optional[int] = None) -> Union[QuickEntry, Unclear, None]:
    """
    Read "<category> <amount> [note]", or say why the amount is unclear.

    An optional date may lead. The amount splits the line: what comes before it
    is the category, so multi-word names work; what comes after is the note. If
    the amount leads instead, the next single word is the category. A number
    that counts things ("۲ عدد") is a quantity, kept in the note, never the
    amount; two bare numbers with no such word between are asked about.

    `prefer` is which of the figures that were asked about is the amount, by
    position — set only by `resolve`, when the person has pointed at one. It is
    the answer to the question, never a default: with no `prefer`, a line that
    could mean two sums is still refused.
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None

    tokens = raw.split()
    if len(tokens) < 2:
        return _lonely_amount(tokens)

    # Two tokens are enough for a back-dated line: «1404/12/28 250000». While
    # this needed three, the shortest one a person can write recorded the date
    # as the category and created that category in the book.
    on = None
    leading = parse_date(tokens[0], today)
    if leading is not None:
        on = leading
        tokens = tokens[1:]

    if len(tokens) < 2:
        return _lonely_amount(tokens)

    # Every number in the line, left to right, with quantities set aside.
    found: List[Tuple[int, int, Decimal, str]] = []
    quantities: List[Tuple[int, int]] = []
    position = 0
    while position < len(tokens):
        read_amount = _amount_at(tokens, position)
        if read_amount is None:
            position += 1
            continue
        if isinstance(read_amount, Unclear):
            return read_amount
        value, width, typed = read_amount
        after = tokens[position + width] if position + width < len(tokens) else ""
        if after in _QUANTITY_WORDS:
            quantities.append((position, position + width + 1))
            position += width + 1
            continue
        found.append((position, width, value, typed))
        position += width

    if not found:
        negative = _negative(tokens)
        if negative is not None:
            return Unclear("negative", (negative,))
        grouped = _dot_grouped(tokens)
        return Unclear("dots", (grouped,), _dot_readings(grouped)) if grouped else None

    index, width, amount, typed = found[0]
    if prefer is not None and 0 <= prefer < len(found):
        index, width, amount, typed = found[prefer]
        # Then the figures nobody pointed at are not amounts. They travel in
        # the note, which is where a counted quantity already goes: «خرید 2 نان
        # 20000» with 20,000 chosen is 2 نان, bought for 20,000 — the same
        # reading «خرید 2 عدد نان 20000» gets, where «عدد» says so out loud.
        quantities += [(start, start + span) for start, span, _, _ in found
                       if start != index]

    problem = _malformed_digits(typed)
    if problem:
        figure = _without_money_word(typed)
        return Unclear(problem, (figure,), _dot_readings(figure) if problem == "dots" else ())
    if prefer is None and len(found) > 1 and amount < 1000 \
            and amount == amount.to_integral_value() \
            and " " not in typed and not re.search(r"\D", to_ascii_digits(typed)):
        # A small bare number followed by more words and another number is as
        # likely a count as a price ("خرید ۲ نان ۲۰۰۰۰"). A large or unit-bearing
        # first number is trusted, since notes legitimately carry numbers too.
        return Unclear("several", tuple(item[3] for item in found[:3]),
                       tuple(item[2] for item in found[:3]))
    if amount <= 0:
        return Unclear("zero", (typed,))

    before = tokens[:index]
    after = tokens[index + width:]
    if after and after[0] in _TOMAN_WORDS:
        after = after[1:]
    elif after and after[0] == "ریال":
        # Rials are a tenth of the toman this book counts in. Converting
        # silently would be a guess; refusing it is a question.
        return Unclear("rial", (typed,))

    # Only counts that come before the amount describe it; a count after it is
    # already part of the note.
    quantities = [span for span in quantities if span[1] <= index]
    if quantities:
        # What was counted travels in the note: "۲ عدد نان" explains 20,000.
        first_start = quantities[0][0]
        counted_at = {i for start, end in quantities for i in range(start, end)}
        lead = tokens[:first_start]
        if lead:
            category = " ".join(lead)
            counted = tokens[first_start:index]
        else:
            # Nothing names the thing, so the words outside the counts do.
            category = " ".join(
                tokens[i] for i in range(first_start, index) if i not in counted_at
            )
            counted = [tokens[i] for i in sorted(counted_at)]
        # Digits are written one way on every screen, whatever keyboard typed them.
        counted_text = to_ascii_digits(" ".join(counted))
        note = " ".join(part for part in (counted_text, " ".join(after)) if part) or None
    elif before:
        category = " ".join(before)
        note = " ".join(after) or None
    else:
        if not after:
            # An amount with nothing to call it: asked, not shrugged at.
            return Unclear("nocategory", (typed,))
        category = after[0]
        note = " ".join(after[1:]) or None

    category = category.strip()
    if not category:
        return None

    return QuickEntry(category=category, amount=amount, description=note, on=on)


def parse(text: str, today: Optional[date] = None) -> Optional[QuickEntry]:
    """The entry when the line is clear; None when it is unreadable or unclear."""
    result = read(text, today)
    return result if isinstance(result, QuickEntry) else None


def resolve(text: str, index: int,
            today: Optional[date] = None) -> Union[QuickEntry, Unclear, None]:
    """The entry the person meant, once they have pointed at one of the readings.

    `read` refuses a line it cannot read one way and names the readings; this
    is what a button offering one of them runs. The line is read again from
    scratch rather than rebuilt from what the button carried — a callback is
    sixty-four bytes of data coming back off somebody's screen, and the typed
    line is the thing that was actually said.

    Still a refusal when the tap does not settle it: an index the line never
    offered, or a line that refuses for a second reason once this one is gone.
    """
    refusal = read(text, today)
    if not isinstance(refusal, Unclear) or not 0 <= index < len(refusal.amounts):
        return refusal

    if refusal.reason == "several":
        # Several figures, each of which could be the amount. Which one was
        # pointed at is the whole answer; `read` needs no rewriting to take it.
        return read(text, today, prefer=index)

    # One figure, two ways to read it. It is written back in plain digits and
    # the line read again, so the fix travels the same path a line typed that
    # way does — no second reader of a line, and no second set of rules.
    plain = f"{refusal.amounts[index]:f}"
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return read(to_ascii_digits(text).replace(refusal.numbers[0], plain, 1), today)
