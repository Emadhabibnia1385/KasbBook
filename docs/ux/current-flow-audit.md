# KasbBook bot — current flow audit (branch `ux-platform-redesign`)

> **Note (2026-10-11):** `screens.py:NNN` and `conversation.py:NNN` references
> below point at the tree as it was audited. Both files have since been split
> by feature into `bot/screens/` and `bot/features/`. The references are kept
> as the evidence they were, not updated to new line numbers.

Method: the real `Conversation.handle()` driven with `IncomingEvent`s (fixture pattern of
`tests/test_conversation.py`), SQLite in memory, no product code touched. Transcripts:
`docs/ux/transcripts/before/*.md` (01–08 journeys, 96 invalid input, 97–99 cancel/stale).
`SCR` = `C:/Users/YEKTAP~1/AppData/Local/Temp/claude/C--Users-Yekta-PC-Desktop-KasbBook/b1642ee6-e4ff-464d-bbcc-ac4105780184/scratchpad/ux`
(run any repro with `./venv/Scripts/python "$SCR/<file>.py"`; `harness.py` is the shared driver).
Steps count every tap or typed line after `/start` (T = typed). Severity: S1 misleads about money/data,
S2 loses/blocks work, S3 confusing, S4 polish.

## 1. Journey table

| Journey | Steps now | Target | Back | Cancel | Error quality | Stale / double-tap |
|---|---|---|---|---|---|---|
| J1 first run → first book → first tx → result | **13** (4 T): tx, single, new-book, type, T name, *Back*, tx, single, today, type, T category, T amount, T note | 4 | Date/type Back → `tx:new` (flow root); no Back inside any prompt | "انصراف" → home; **new-book cancel leaks (B5)** | blank/300-char/duplicate book names accepted (B6) | n/a |
| J2 quick entry (`فروش ۲۵۰ک`) | **2** (T + tap income/expense); 3 with 2 books; **no book: line discarded, 5+ steps then retype** | 1–2 | no Back, only انصراف→home | ok | unreadable line: examples shown but no cause; wrong amount read silently (B3) | **old confirm button acts on newest draft (B1)**; concurrent tap records twice (B2); sequential 2nd tap → silent jump to home |
| J3 single button entry | **7** (1 book) / 8 (2 books): tx, single, [book], today, type(4 choices), category, T amount, skip | 3 | Date/type Back → `tx:new`; category/amount/note have none | انصراف → home (drops draft; correct but far) | amount `abc` re-asks with identical text; `0` accepted then fails (B4) | `tx:skip` after save → silent tx menu; no double-record sequentially |
| J4 daily list → find → edit / delete | edit **5**, delete **5** (confirm), find **4 then dead end** | 3 / 3 / 4 | list→`tx:new`; detail→list; search→book menu (real parents) | edit cancel → home, not the transaction | edit amount: specific causes (good); search 1 char re-asks silently | deleted tx buttons → "پیدا نشد" + home only; search results have **no row buttons** |
| J5 report + CSV | **4**: reports, book (asked even with 1 book), period, CSV | 2 | summary "Back" is "منوی اصلی", not the period menu; breakdown Back OK | n/a | empty period: all zeros, no guidance; empty CSV (header only) exported silently | CSV tap re-renders same summary, file arrives separately, no ack |
| J6 budget | **6** (1 T): books, book, budget, set, kind, T amount | 3 | Back → book menu | انصراف → home | `abc` re-asks, shows raw **`expense`** (B10); `0` → error + dead end | 🗑 deletes budget with **no confirm**; name label is `noop` → home (B7) |
| J7 debt | **8** (3 T): books, book, debts, add, T name, direction, T amount, T due | 4 | Back → book menu | انصراف → home | text at button step re-asks silently; "ندارد" rejected (B9) | settle/delete no confirm; settled item vanishes under "چیزی ثبت نشده" |
| J8 recurring | **9** (3 T): books, book, recurring, add, flow, T category, T amount, period, T start | 4 | Back → book menu | انصراف → home | `abc`/`0`/"هر ماه" silent re-ask; start prompt has no format | rule name label `noop` → home; ⏸/🗑 no confirm; "today" uses server day (B11) |

Cross-journey: every book-scoped feature (budget, debt, loan, recurring, search, categories, wallet) is
home → دفترهای من → book → feature, **3 taps deep** even with one book. `/help` and any unknown command
just redraw the welcome (conversation.py:178-184).

## 2. CONFIRMED BUGS (reproduced)

**B1 — S1 — stale quick-entry button records the newest draft.** Type `فروش 100000`, then `اجاره 9000000`,
then tap *درآمد* on the first message: records `اجاره 9,000,000` as income. `_quick_callback`
(conversation.py:2020-2050) reads whatever draft is current; buttons carry no draft id. Same shape for
`tx:skip` / `tx:cat:N` (conversation.py:287-402). Repro: `SCR/repro_stale_quick.py` (`98-stale-quick.md`).

**B2 — S1 — double-tap records twice when updates are concurrent (webhook mode).** Two simultaneous
`qk:flow:income`: 1 → 3 transactions on an existing category; on a *new* category the loser dies with an
unhandled `IntegrityError` (user sees nothing). Webhook handler gives each request its own session and
shares the state store, no per-user lock, no idempotency (api/routers/webhooks.py:76-83;
`ledger.record`). Polling is sequential (apps/bot/runner.py:199) and is not affected. Repro:
`SCR/repro_double_tap.py`.

**B3 — S1 — the quick parser reads the wrong amount without saying so.** `خرید ۲ عدد نان ۲۰۰۰۰` → 💵 2;
`قهوه ۳۰ هزار و ۵۰۰` → 30,000 with note "و ۵۰۰"; `1,5` → 15 (comma is a thousands separator,
shared/parsing.py:47). First number wins (bot/quick.py:57-72). The confirm screen shows category + amount only —
never the note, date (`دیروز` is applied silently) or book (screens.py:901-908). Repro: `SCR/t_quick2.py`, `SCR/inv2.py`.

**B4 — S2 — zero amount accepted, then an English error traps the flow.** `_tx_text` never checks `> 0`
(conversation.py:2187-2192), description step "succeeds" into `ledger.record` which raises
`an entry of zero moves nothing` (ledger/service.py:191). The user sees `⚠️ an entry of zero moves nothing`
with only «منوی اصلی»; every later line is swallowed as a description and fails identically. (Edit-amount
checks `> 0` properly.) Repro: `SCR/inv2.py`, `96-invalid-input.md`.

**B5 — S2 — "انصراف" on the new-book name prompt does not cancel.** It sends `book:list`, which does not clear
state (screens.py:149, conversation.py:268-285), so the next typed line (`فروش 250000`) becomes a book.
Sweep of 14 other prompts: all others clear correctly. Repro: `SCR/repro_cancel_book.py`, `SCR/cancel_sweep.py`.

**B6 — S2 — book names unvalidated.** Blank (empty button label), 300 chars, duplicates (two identical
"مغازه" buttons — money can go to the wrong one). conversation.py:1934-1937, books/service.py:37.
Repro: `SCR/repro_book_name.py`.

**B7 — S3 — "inert" labels navigate home.** `noop:*` returns the welcome screen (conversation.py:257-259,
comment says "the screen stays"). Hit by tapping a budget/recurring/debt name (screens.py:983) and the
search page counter (screens.py:1395). Repro: `SCR/j6_budget.py` (`06-budget.md`).

**B8 — S3 — "✅ ثبت شد" glued to the next line.** `rtl("✅ ثبت شد\n")` — `splitlines()` drops the trailing
newline (screens.py:42, conversation.py:2244): output `✅ ثبت شد🧾 جزئیات تراکنش`. Every full-flow save.

**B9 — S3 — debt due prompt lies.** "تاریخ بنویس، یا «ندارد» بزن." but typing ندارد re-asks forever
(screens.py:1061, conversation.py:2086). Repro: `SCR/t_nodue.py`.

**B10 — S3 — English leaks.** Budget re-ask shows `«expense»` (conversation.py:2063 passes the raw target to
screens.py:1003); B4's domain error is English; `ledger` messages reach users through `screens.error`.

**B11 — S3 — server day, not the person's day** (code-read; not reproduced, needs a tz edge): `date.today()`
at conversation.py:725 (recurring "today"), 776 (budget month), 898 (loan), 1353, 1398; `parse_date(text)` with
no `today` at 2086, 2113, 2135 ("فردا"/"امروز" relative to the server). The constitution's own rule is `_today(user)`.

**B12 — S2 — search is a dead end.** Results list has no per-row buttons, so find → edit is impossible
(screens.py:1370-1401). Short query (<2 chars) re-asks silently (conversation.py:1955). `04-daily-find-edit-delete.md`.

Unverified risk (S2): `Money` is `Numeric(28,4)`; the parser accepts a 24+ digit amount (`999999999999999999999999`
saved on SQLite). On PostgreSQL a longer one raises a non-domain error; the runner swallows it and the user gets no reply
(runner.py:136-140, webhooks.py:84-87).

## 3. Other findings

**S2**
- F1 First run dead end: creating the first book lands on the book list, not "now record your first transaction"
  (conversation.py:1934-1937). Welcome never says a book is needed first (screens.py:65-73). Account is silently
  auto-created on first `/start` (conversation.py:166-173): no sentence about what was created or how to link web.
- F2 No step-back inside any wizard: wrong category/amount means انصراف → restart (13 steps for J1 in total).
  انصراف always goes to `nav:home` (screens.py:215-447), never to the parent (edit prompt, budget, debt, recurring).
- F3 Destructive actions without confirmation: budget 🗑, debt settle/delete, recurring ⏸/🗑 (conversation.py:707-735,
  845-855). Only transaction delete asks. Settling shows "چیزی ثبت نشده" (looks like data loss).
- F4 Stale buttons silently reroute to home/other screen with no "expired" sentence (conversation.py: 45 `return
  screens.welcome(...)` fallbacks). After a 30-min expiry a typed amount gets the quick-entry help ("متوجه نشدم")
  with no "your draft expired". Crafted/garbled callbacks raise `ValueError` (S4: only a forged payload).

**S3**
- F5 Date step on every single entry (`pick_date`) and a 4-way type menu ("درآمد کاری/هزینه کاری/درآمد شخصی/
  هزینه شخصی", screens.py:158-170) on a business book: scope jargon before the user has typed a word.
- F6 Two different success screens (quick: `ثبت شد.` + "ثبت بعدی"; full flow: detail card with no "ثبت بعدی").
  Detail card noise: seconds in time, `رسید: ندارد`, `ثبت‌شده توسط` (screens.py:1228-1250). No effect on balance/month
  shown anywhere.
- F7 Silent re-asks (cause not stated): amount (conversation.py:2185), date (2169), rate (2166), debt amount/due
  (2078, 2087), recurring amount/start (2124, 2136), search, text typed at a button-only step (debt direction,
  recurring period).
- F8 Edit success shows the card with no "✅ ویرایش شد"; edit prompts don't show the current value.
- F9 Daily list: jargon "پس‌انداز عملیاتی / نهایی", "قسط پرداختی", "خالص کاری" (screens.py:285-296); a dense
  screen with 8+ button rows; header leads with Gregorian `2026-10-11 | 1405/07/19` (screens.py:325).
- F10 Reports offer only this/last week, current month, year — no last month; empty period = zeros without a hint;
  CSV amounts carry `.0000`, ids truncated to 8 chars (cosmetic S4).
- F11 Digits: all dynamic numbers/dates are Latin (`fmt`, `jalali.to_text`, counts "3 مورد", "60%") while static
  hints are Persian (`۲۵۰ک`) — often both in one line (screens.py:445). Currency shown as code `IRT`, not تومان.
  (Tests assert `"500,000" in reply.text`; a digit layer needs the tests updated deliberately.)
- F12 Emoji: ~460 in screens.py; detail card 18, account panel 18, period detail 15, book menu 13 (one per button);
  📄 used for both تراکنش‌ها and وام و اقساط; every book button prefixed "💼 کسب‌وکار …" so a book named
  "مغازه" reads as a phrase (screens.py:112, 131).
- F13 Prompts without an example: ask_book_name, recurring_ask_start, debt_ask_amount, budget amount, search.
  `12.5555` is stored to 4 dp but displayed as `13` (fmt rounds, screens.py:45-47).

**Good (keep):** ZWNJ is correct everywhere I scanned (0 missing `می‌/نمی‌`, 0 Arabic ي/ك in screens.py and
conversation.py); amount parser handles Persian digits/`ک`/`م`; delete-transaction confirm; edit-amount errors name
the cause; daily list Prev/Next/Today; callbacks use short codes and indices (64-byte rule respected).

## 4. Top-10 ranked problems

| # | Pri | Problem | Evidence |
|---|---|---|---|
| 1 | P0 | Stale quick/wizard confirm button acts on the newest draft (wrong money recorded) | B1 |
| 2 | P0 | Concurrent double-tap records twice; first-use category race crashes silently (webhook mode) | B2 |
| 3 | P0 | Quick parser mis-reads amount (`۲ عدد نان ۲۰۰۰۰`, `۳۰ هزار و ۵۰۰`, `1,5`) and confirm hides note/date/book | B3 |
| 4 | P0 | Zero amount accepted → English error trap; same family of English/raw-enum leaks | B4, B10 |
| 5 | P0 | "انصراف" does not cancel new-book; typed line becomes a book; names unvalidated/duplicated | B5, B6 |
| 6 | P1 | First run is 13 steps with a dead end after creating the first book; target 4 | J1, F1 |
| 7 | P1 | No step-back in wizards; cancel always goes home; book-scoped features 3 taps deep | F2, table |
| 8 | P1 | Search is a dead end (no row buttons); report asks book even with one book; 4 taps to CSV | B12, J5 |
| 9 | P1 | Silent re-asks and lying prompts («ندارد», `noop` buttons going home); no "expired" message | F7, B7, B9, F4 |
| 10 | P1 | Destructive/finishing actions without confirmation or acknowledgement (settle, delete budget/rule, edit) | F3, F8 |

## 5. Terminology glossary (one word per concept)

| Concept | Use | Stop using / where it varies |
|---|---|---|
| ledger container | **دفتر** | "حساب" only for the user account (**حساب کاربری**, not "حساب من"); type labels: «کسب‌وکار» everywhere (button says "کسب‌وکار شخصی", label says "کسب‌وکار", screens.py:24 vs 141) |
| one entry | **تراکنش** | "ثبت تکی" (opaque) → "ثبت تراکنش"; "قاعده" → "تراکنش تکرارشونده" |
| category | **دسته** (list name: «دسته‌ها») | "دسته‌بندی" (6×) and "دستهٔ" (7×) mixed in screens.py and conversation.py |
| income / expense | **درآمد / هزینه** | drop "کاری/شخصی" qualifiers in business books; "خالص" → "سود" in daily view |
| abort a form | **انصراف** (↩️, on input prompts only) | "لغو" only appears for payments (screens.py:760, 1953) → "برگرداندن پرداخت" |
| one level up | **بازگشت** (⬅️) | «منوی اصلی» as a back label, «دفترها»/«دفتر» as back labels (see book_menu, screens.py:930+), «برگشت» |
| record / create | **ثبت** (money facts), **ساخت** (book), **افزودن** (list item) | "تعیین بودجه" → "ساخت بودجه" |
| debt directions | **طلب من / بدهی من** everywhere | "به من بدهکار است / من بدهکارم" buttons (screens.py:1048-1054) |
| delete | **حذف** | "پاک کردن" (screens.py:1285) |

## 6. Persian rewrites (priority order, ≤25)

| # | Where | Current → proposed |
|---|---|---|
| 1 | conversation.py:2244 | `"✅ ثبت شد\n"` (newline lost) → `"✅ ثبت شد\n\n"` + a join that keeps the blank line; then `🧾 جزئیات` |
| 2 | screens.py:455 | `✅ ثبت شد.` → `✅ درآمد ۲۵۰٬۰۰۰ تومان ثبت شد` + lines `🏷 فروش · 📚 مغازه · 📅 ۱۴۰۵/۰۷/۱۹` + note if any |
| 3 | screens.py:901 (quick confirm) | `🏷 فروش / 💵 250,000 / درآمد است یا هزینه؟` → `فروش — ۲۵۰٬۰۰۰ تومان — ۱۹ مهر — دفتر مغازه` + `همین را ثبت کنم؟ درآمد یا هزینه؟` (note shown) |
| 4 | screens.py:126 | `برای ثبت تراکنش اول باید یک دفتر بسازی.` → `هنوز دفتری نداری. اول یک دفتر بساز (مثلاً «مغازه»)، بعد تراکنش‌هایت را در آن ثبت کن.` |
| 5 | screens.py:149 | `اسم این دفتر چه باشد؟ نوع: …` → `اسم دفتر را بنویس.\nمثال: مغازه، خرج خانه، تیم طراحی` |
| 6 | screens.py:65-72 | `از منوی زیر شروع کن 👇` → `برای شروع بنویس: «فروش ۲۵۰ک» — یا از منوی زیر استفاده کن.` (first run: «اول یک دفتر بساز») |
| 7 | screens.py:438-445 | `مبلغ را بنویس. می‌توانی این‌طور هم بنویسی: ۲۵۰ک، 1.2م، 250,000` → `مبلغ را بنویس؛ مثلاً ۲۵۰۰۰۰ یا ۲۵۰ک یا ۱٫۲م` |
| 8 | conversation.py:2185 (re-ask) | same prompt again → `⚠️ «abc» مبلغ نیست. فقط عدد بنویس؛ مثلاً ۲۵۰۰۰۰ یا ۲۵۰ک.` |
| 9 | conversation.py:2187 + ledger | `⚠️ an entry of zero moves nothing` → `⚠️ مبلغ باید بیشتر از صفر باشد.` (check at the amount step; keep the prompt) |
| 10 | screens.py:229-235 | `مثال: 1404/12/28 یا 2026-03-19` → `مثال: ۱۴۰۴/۱۲/۲۸ یا «دیروز»`; on re-ask prefix `«فردا یا پس‌فردا» را نفهمیدم.` |
| 11 | screens.py:1061 | `تاریخ بنویس، یا «ندارد» بزن.` → `تاریخ بنویس (مثلاً ۱۴۰۵/۰۸/۱۵) یا دکمهٔ «بدون سررسید» را بزن.` |
| 12 | screens.py:1468 | `از چه تاریخی شروع شود؟` → `از چه تاریخی شروع شود؟ مثلاً ۱۴۰۵/۰۸/۰۱ یا «فردا»؛ یا «امروز» را بزن.` |
| 13 | screens.py:1003 | `سقف ماهانه برای «expense» چقدر باشد؟` → `سقف ماهانهٔ «هزینه‌ها» چقدر باشد؟ مثلاً ۵۰۰ک یا ۲ میلیون` |
| 14 | screens.py:911-921 | `❓ متوجه نشدم.` → `❓ مبلغی در این پیام ندیدم.` keep examples; add `یا دکمهٔ «ثبت تراکنش» را بزن.` |
| 15 | screens.py:205-210 | `➕ ثبت تکی — یک تراکنش، با هر تاریخی` → `➕ ثبت تراکنش — قدم‌به‌قدم`; `📅 لیست روزانه — همهٔ دفترهایت، روز به روز` → `📅 تراکنش‌های هر روز — دیدن، ویرایش، حذف` |
| 16 | screens.py:158-170 | `💰 درآمد کاری / 🏢 هزینه کاری / 💵 درآمد شخصی / 👤 هزینه شخصی` → `💰 درآمد / 🧾 هزینه` (+ «برداشت شخصی» only where scope matters) |
| 17 | screens.py:285-296 | `💾 پس‌انداز عملیاتی / نهایی`, `➖ خالص کاری` → `💾 مانده پس از هزینه‌ها`, `➖ سود کاری` (and drop `قسط پرداختی: 0` rows when zero) |
| 18 | screens.py:325, 1233 | `📅 2026-10-11  \|  1405/07/19` → `📅 ۱۴۰۵/۰۷/۱۹` (Gregorian only on request/in CSV) |
| 19 | screens.py:112, 131, 141 | `💼 کسب‌وکار مغازه` button → `💼 مغازه`; `کسب‌وکار شخصی` → `کسب‌وکار` |
| 20 | screens.py:1048-1054 | `📥 به من بدهکار است / 📤 من بدهکارم` → `📥 طلب من (او بدهکار است)` / `📤 بدهی من (من بدهکارم)` |
| 21 | conversation.py:595, 739, 857, 1304 | `⚠️ این تراکنش پیدا نشد` → `این مورد دیگر وجود ندارد (شاید حذف شده).` + button `⬅️ بازگشت به لیست` (error() takes a back target, screens.py:925) |
| 22 | conversation.py (45 welcome fallbacks) | silent jump → `این دکمه قدیمی است؛ ادامه از همین‌جا:` above the target screen |
| 23 | screens.py after settle/edit | `چیزی ثبت نشده.` → `✅ تسویه شد. مورد بازی نمانده.`; edit card prefixed `✅ ویرایش شد` |
| 24 | conversation.py:1955 / screens.py:1364 | silent re-ask → `حداقل دو حرف بنویس.`; results rows tappable, `1 نتیجه` → `۱ نتیجه` |
| 25 | screens.py:760, 1953 | `هر چیز دیگری بنویسی، لغو می‌شود` / `↩️ لغو آخرین پرداخت` → `…، انصراف حساب می‌شود` / `↩️ برگرداندن آخرین پرداخت` |

## 7. Not tested / limits
Provider adapters, real Telegram edit-in-place and message deletion (runner removes the user's typed line, so
old bot messages are the only thing left on screen — which is what makes B1 reachable). Loans, payroll, treasury,
reminders, account/web-link and invitation flows were only glanced at. PostgreSQL behaviour is inferred from the
column type, not run.
