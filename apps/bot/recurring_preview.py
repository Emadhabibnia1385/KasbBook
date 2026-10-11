"""What the next recurring run would book — without booking it.

    python apps/bot/recurring_preview.py            # as of today
    python apps/bot/recurring_preview.py 2026-10-11 # as of a given day

For the operator, before switching `KASBBOOK_RECURRING` on after a long pause
or an upgrade. It does not imitate the run: it performs the real one in a
transaction and rolls it back, so what it prints is exactly what the bot would
do, refusals and pauses included, and nothing is written.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kasbbook.modules.books.models import Book  # noqa: E402
from kasbbook.modules.recurring.service import RecurringService  # noqa: E402
from kasbbook.shared import jalali  # noqa: E402
from kasbbook.shared.database import Database  # noqa: E402
from kasbbook.shared.settings import Settings  # noqa: E402


async def preview(database: Database, until: Optional[date] = None) -> str:
    """The report, as text. The session is rolled back whatever happens."""
    day = until or date.today()
    lines: List[str] = [f"Recurring run as of {day.isoformat()} ({jalali.to_text(day)}) — preview, nothing written", ""]

    async for session in database.session():
        try:
            run = await RecurringService(session).run_due(until=day)

            books = {}
            for rule, tx in run.booked:
                books.setdefault(rule.book_id, {"booked": {}, "skipped": {}, "paused": []})
                books[rule.book_id]["booked"].setdefault(rule, []).append(tx.occurred_on)
            for rule, when in run.skipped:
                books.setdefault(rule.book_id, {"booked": {}, "skipped": {}, "paused": []})
                books[rule.book_id]["skipped"].setdefault(rule, []).append(when)
            for rule in run.paused:
                books.setdefault(rule.book_id, {"booked": {}, "skipped": {}, "paused": []})
                books[rule.book_id]["paused"].append(rule)

            for book_id, found in books.items():
                book = await session.get(Book, book_id)
                lines.append(f"Book {book.name if book else book_id} ({book_id})")
                for label, rules in (("would book", found["booked"]),
                                     ("would skip (closed period)", found["skipped"])):
                    for rule, dates in rules.items():
                        lines.append(
                            f"  {label}: {rule.category} {rule.flow.value} "
                            f"{rule.amount:,.0f} x{len(dates)}, "
                            f"{min(dates).isoformat()} .. {max(dates).isoformat()}"
                        )
                for rule in found["paused"]:
                    lines.append(f"  would pause: {rule.category} {rule.flow.value} "
                                 f"(its author can no longer book it here)")
                lines.append("")

            lines.append(
                f"Total: {len(run.booked)} transaction(s) booked, "
                f"{len(run.skipped)} date(s) skipped, {len(run.paused)} rule(s) paused."
            )
        finally:
            # The only line that matters: nothing this run did may survive it.
            await session.rollback()
    return "\n".join(lines)


async def main(argv: List[str]) -> None:
    until = date.fromisoformat(argv[1]) if len(argv) > 1 else None
    database = Database(Settings.from_env().database_url)
    try:
        print(await preview(database, until))
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
