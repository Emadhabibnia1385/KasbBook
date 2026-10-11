"""Reports in the bot: a book, a period, the summary, the category breakdown, the CSV.

The figures come from ReportService, the same one the API calls; this feature
only chooses which period to ask it about and draws the answer.
"""

from __future__ import annotations

import uuid

from ...adapters.base import OutgoingFile
from ...modules.reports import service as reports_service
from .. import screens
from .base import Feature


class ReportsFeature(Feature):
    prefixes = ("rep", "rp", "rb", "rc")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "rep":
            return await self._report_callback(action, argument, user)
        # rp, rb and rc all name a book and a period the same way.
        return await self._period_screen(parts, user, area)

    async def _report_callback(self, action: str, argument: str, user):
        if action == "book":
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            years = await self.ctx.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years, self.ctx.today(user))

        return screens.report_menu(await self.ctx.books.books_for_user(user.id))

    async def _period_screen(self, parts, user, kind: str):
        """rp / rb / rc all name a book and a period the same way."""
        book = await self.ctx.books.get_book(uuid.UUID(parts[1]))
        spec = ":".join(parts[2:])
        period = reports_service.parse_spec(spec)
        if period is None:
            years = await self.ctx.reports.years_with_data(book.id, user.id)
            return screens.period_menu(book, years, self.ctx.today(user))

        if kind == "rb":
            buckets = await self.ctx.reports.by_category(book.id, user.id, period)
            return screens.category_breakdown(book, period.label, buckets, spec)

        if kind == "rc":
            payload = await self.ctx.reports.to_csv(book.id, user.id, period)
            self.ctx.pending_file = OutgoingFile(
                content=payload,
                filename="kasbbook-" + spec.replace(":", "-") + ".csv",
                caption="خروجی " + period.label,
            )
            summary = await self.ctx.reports.summary(book.id, user.id, period)
            return screens.period_report(book, period.label, summary, spec)

        summary = await self.ctx.reports.summary(book.id, user.id, period)
        comparison = None
        compared = await self.ctx.reports.compare(book.id, user.id, period)
        if compared is not None:
            previous, before, after = compared
            comparison = screens.comparison_line(previous.label, before, after)

        return screens.period_report(book, period.label, summary, spec, comparison)
