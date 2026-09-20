"""Where a live exchange rate comes from.

Kept out of `modules/` on purpose: every service in this project talks to the
database and nothing else, and a rule that silently depends on a third party
being reachable is a rule that fails at the worst moment. A rate source is
passed in, so a service without one simply has no quote and asks the person
instead.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Protocol


class RateSource(Protocol):
    async def quote(self, code: str, base: str) -> Optional[Decimal]:
        """One unit of `code` priced in `base`, or None if it is not known."""
        ...


__all__ = ["RateSource"]
