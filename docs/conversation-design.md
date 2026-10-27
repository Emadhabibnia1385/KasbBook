# Conversation design

The bot has no screen of its own. Everything a person sees is a block of text
and a grid of buttons; everything they can do is a tap or a typed line. Two
things follow from that. The vocabulary has to be identical everywhere, because
there is no layout to tell someone where they are — only the words on the
buttons. And every step has to earn the tap it costs, because a conversation is
read downwards with a thumb — though what a step earns is not always the answer
it collects, which is where this got interesting.

This page is the settled part: the navigation vocabulary, how a keyboard is
laid out, what the recording flow assumes and why, and the invariants that stop
a tapped button recording money twice. Which screen says what is in the code,
under `bot/screens/`. What follows is the reasoning, which stays true when a
screen changes.

## One glyph per action, not per module

Three shared rows in `bot/screens/common.py` are the whole navigation
vocabulary, and `bot/screens/__init__.py` re-exports them like every other
screen name:

| | Row | What it means |
|---|---|---|
| `back_row(data)` | ⬅️ بازگشت | up one level, to the parent's own callback |
| `cancel_row(data="nav:cancel")` | ↩️ انصراف | abandon the draft; nothing was recorded |
| `rows_of(buttons, per_row=2)` | — | lay buttons out, at most three to a row |

They exist because the glyph had stopped meaning the action and started
meaning the module. Planning and books wrote «↩️ انصراف» where payroll, account
and wallet wrote «⬅️ انصراف», and the transaction flow managed both inside one
journey. A person tapping ⬅️ in one feature and ↩️ in the next for the same
intent has to re-read every keyboard, which is the cost a consistent vocabulary
exists to avoid.

`↩️` is the canonical cancel, and the reason is worth stating plainly rather
than arguing about: `tests/test_conversation.py` pins a prompt's keyboard to
exactly `["↩️ انصراف"]`. Where two spellings are both defensible, the one a
test already asserts is the one that stays — a test is a decision somebody
already made.

Two details the signatures carry:

- **`back_row` takes the parent's callback, not a constant.** `nav:home` is
  correct only when home really is the parent, which is true just for the main
  menu's own children. Everywhere else, «بازگشت» that lands on the home screen
  is a cancel wearing the wrong glyph.
- **`cancel_row` defaults to `nav:cancel`, which says so.** Cancelling draws
  `cancelled()` — a line confirming that nothing was kept — rather than
  silently redrawing the home screen, because a person who cannot tell a cancel
  from a crash will type the entry again.

## The keyboard grammar

Adopted from the sibling Seamless_bot, where it was settled by use:

1. The screen's primary action keeps its own full-width row.
2. Buttons of equal weight and the same kind pair.
3. A destructive action gets its own row — a thumb aiming at the button beside
   it must not be able to reach it. `confirm_delete()` is built that way.
4. The back or cancel row is last, and alone.
5. Never more than three buttons in a row.

The cap is not aesthetic. A fourth Persian label wraps or is cut on a phone,
and a button whose text is cut is a button whose meaning is guessed.
`rows_of()` enforces it rather than trusting the caller: `per_row` is clamped,
so passing four quietly gives three.

`rows_of` was `_pairs`, private to `bot/screens/transactions.py`, where only
that module's screens could reach it — the screens package is a star around
`common`, and a feature's screens may not import another feature's
(`tests/test_screens_architecture.py` holds that shape). A layout rule that
lives inside one feature is a layout rule the other features have to reinvent,
which is how the inconsistency above happened. It now lives in `common` with
the rest of the shared vocabulary; `_pairs` is an alias of it, kept because the
screens that call it read better for the shorter name.

## Recording: what came out of the flow, and what did not

Measured by driving `Conversation.handle` with `IncomingEvent`s — the fixture
pattern of `tests/test_conversation.py` — for a person with one book in one
currency. Seven interactions became five:

| | Before | Now |
|---|---|---|
| 1 | `tx:new` — a menu that re-asked what the main menu had just asked | tap «📌 ثبت تراکنش», which starts the entry itself |
| 2 | `tx:book` | tap the kind |
| 3 | `tx:on:today` — a date question whose answer is almost always today | the category |
| 4 | `tx:type:we` | the amount |
| 5 | the category | the description, or the button that declines it |
| 6 | the amount | |
| 7 | `tx:skip` | |

Three steps went: the intermediate menu, the book choice when there is only one
book, and the date question. A fourth was taken out and put back, which is the
most instructive of the four.

### The home screen is the menu

`main_menu()` in `bot/screens/common.py` was five stacked full-width buttons,
and its first one opened a menu that only re-asked what had just been tapped.
It is now four rows with peers paired: the one verb on its own row, then the
daily list beside the reports it belongs with, the books beside the reminders,
the account last. The daily list used to be two taps deep behind that
intermediate menu — the screen a shopkeeper opens most often was the hardest
one to reach.

Its button is `dl:v` with no date on it, deliberately. The handler falls back
to the person's own today, so the button needs no date, costs no bytes against
the sixty-four a callback payload has, and cannot go stale on a screen left
open overnight.

### The date is assumed, not asked

The flow used to open with `pick_date`, whose two buttons were «today» and
«another date». A question with one usual answer is a tax on every entry to
serve the rare one.

The day is now taken from the person's today in `_start_single`
(`bot/features/transactions.py`) and the flow opens on `pick_type`. The
assumption is never silent: `pick_type` names the day in its heading, offers
«✍️ تاریخ دیگر» for the exception, and the card that comes back after saving
can still edit the date. An assumption that is stated, correctable before the
fact and correctable after it is not a guess.

### The description step was removed, and put back

Read this one twice, because the argument for removing it was good. The
description is optional, its usual answer was the skip button, and the saved
card already offers «ویرایش توضیحات» and «افزودن رسید» — so the prompt looked
like a blocking screen standing in front of something the person could do
afterwards, or never. Committing on the amount instead makes the flow four
interactions, and for a while it did.

It is five, because that step is not only a prompt for a note. It is also where
a captioned photo completes the entry in one message, and the two routes to a
receipt are not gated alike: `LedgerService.record()` takes a receipt under
`RECORD_INCOME`/`RECORD_EXPENSE`, while `attach_receipt()` afterwards requires
`EDIT_TRANSACTION`. A member who may record but not edit can attach a receipt
only while the entry is being made. Saving on the amount took receipts away
from exactly that member, silently, to buy one tap.

The lesson generalises past this step. A step whose usual answer is a skip
button looks like pure cost, and the tap is the only part of it that is easy to
see. What else the step carries — here, a permission the later path does not
have — is the part you have to go looking for before you delete it.

### Whichever step commits is the step that claims

`_save_tx` takes the draft out of the state store with an atomic `pop` before
it records. Of two copies of that step in flight — a double tap on the skip
button, with webhook mode giving each update its own session and running them
concurrently — one finds a draft and the other is told its message is old. If
`record()` then refuses, the draft is put back: a claim is not a consumption,
and one typo should not cost the whole entry.

What matters is the coupling, not the `pop`. That claim lives in `_save_tx`
because `_save_tx` is where the commit is; while the commit sat on the amount
message, the claim had to sit there too, and moving the commit back moved it
back. A claim one step behind the commit protects nothing, and nothing in the
type system will say so:

> **Whichever step commits is the step that must claim.**

Pinned by
`tests/test_bot_stale_and_cancel.py::test_two_simultaneous_description_skips_record_once`
and `::test_two_simultaneous_quick_confirms_record_once`, which race two
identical updates through two sessions and assert one transaction and one reply
saying the message is old.

## The quick line: a space cannot change what a line means

`bot/quick.py` reads a whole transaction out of one typed line — «فروش 250ک»
— and it is the only path that records without a confirmation step. That makes
its failures different in kind from a screen's: there is nobody to notice.
Everything it refuses, it refuses by asking (`unclear_reason()` in
`bot/screens/common.py` says which reading was unclear and shows one that
works). Four invariants, each of which it once broke:

**Whatever the parser accepts glued to the digits, it accepts beside them.**
«فروش 250 ک» recorded 250 toman instead of 250,000, silently, with «ک» filed
as the description — a thousand-fold undercount. The list of magnitudes that
may follow a number as a separate word held only the spelled-out ones
(«هزار», «میلیون»), while `parse_amount` in `shared/parsing.py` also accepts
`ک/م/ب/k/m/b` glued to the digits. One space dropped the multiplier. That list
is now derived from the single table `parse_amount` reads, so the two cannot
drift apart again, and
`tests/test_quick_and_reports.py::test_a_space_before_the_unit_does_not_divide_the_amount_by_a_thousand`
checks every unit in that table both ways.

**The shortest line a person can write still parses.** «1404/12/28 250000» —
a date and an amount — recorded the date as the category name and created that
category in the book, because the leading-date strip was gated on more than two
tokens. Two is enough.

**A line with an amount is never missing an amount.** «250000» alone answered
"I saw no amount in this message", which was the one thing it certainly had.
What was missing was the category, and that is what it now asks for. Anything
that is not an amount stays unreadable, so ordinary chat is not answered with a
nag.

**An ambiguous figure is asked about, never read.** «1.500.000» is the
commonest Persian way of typing one and a half million; `parse_amount` refuses
two dots, so the line came back as unreadable — the one refusal that teaches
nothing. It is now asked about, as rials are, because choosing a reading
silently is a guess about money. The question is also asked about the figure
that was typed: it used to name 250 whatever it had been handed, so «1.500.000»
would have been answered with two readings of a number nobody had written.

## Where user-facing copy lives

Domain errors reach the bot in whatever language the service wrote them.
`user_message()` in `bot/screens/common.py` is the boundary: an English message
is mapped to a Persian sentence with a way forward, and a message that already
contains Persian is passed through **verbatim**, on the reasonable assumption
that a service writing Persian wrote it for a person.

That pass-through is the trap. `modules/ledger/categories.py` wrote
«دسته‌بندی» in every refusal it raises — the exact word
`tests/test_bot_ux_fixes.py::test_the_vocabulary_is_one_word_per_concept`
forbids, because one concept gets one word — and one sentence managed to use
both «دسته‌بندی» and «دستهٔ» at once. Two of them also wrote Persian digits,
which `test_user_facing_digits_are_written_one_way` forbids for the same
reason. Every one of those sentences reached users unaltered, and no guard
noticed, because the copy guards read only the files under `bot/`.

The class of bug, worth more than the instance:

> **A service-layer error message is user-facing copy.**

It is written in a service, where the project's rules say rules belong, and
read on a phone, where the project's copy rules apply. If it is Persian, it is
copy.

So the guards were widened rather than the word merely corrected.
`tests/test_copy_rules.py` holds the same vocabulary, half-space and digit
rules over `modules/` and `shared/`. It finds the surface instead of guessing
it: an AST walk collects the first argument of every call to a class
`shared/errors.py` defines, which is exactly what reaches `user_message()`. A
regex over the sources would have swept up comments and docstrings nobody
reads, and missed a message held in a module constant. It also asserts a floor
on how much copy the walk found, so a walk that silently stops seeing the
service layer — because a service began raising through a helper it does not
follow — fails loudly instead of passing every rule on an empty list.

## Where to read more

- The shape of `bot/features/` and `bot/screens/`, and what a screen may
  import: [architecture.md](./architecture.md).
- The checklist for adding a screen, and the guard tests:
  [development.md](./development.md).
- What this redesign was measured against, journey by journey, with the
  transcripts it was measured from: `docs/ux/current-flow-audit.md` and
  `docs/ux/redesign-plan.md`. Both are dated audits — evidence of a tree as it
  was, not a description of the one you have.
