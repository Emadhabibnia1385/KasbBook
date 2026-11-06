"""One place to ask what a currency is worth, for the bot and for anything else that has a book.

`SwapWalletRates.quote` only knew crypto and the toman. This puts the two feeds behind the same
`quote(code, base)` the wallet and the transaction flow already call, so every currency in the
catalog gets a rate where one can be had, and `quote_detail` says whether it is a price the market
publishes or an estimate (see `quote.py`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from .fiat import OpenErRates
from .quote import Quote, quote as compute
from .swapwallet import SwapWalletRates


class MarketRates:
    def __init__(self, crypto: Optional[SwapWalletRates] = None, fiat: Optional[OpenErRates] = None) -> None:
        self.crypto = crypto or SwapWalletRates()
        self.fiat = fiat or OpenErRates()

    async def quote_detail(self, code: str, base: str) -> Optional[Quote]:
        prices = await self.crypto.prices()
        per_usd = await self.fiat.per_usd()
        return compute(prices, per_usd, code, base, getattr(self.crypto, "_fetched_at", None), self.fiat.fetched_at)

    async def quote(self, code: str, base: str) -> Optional[Decimal]:
        found = await self.quote_detail(code, base)
        return found.value if found else None

    async def table(self, codes: Sequence[str], base: str) -> List[Tuple[str, Quote]]:
        """The codes that can be priced in `base`, in the order asked; the rest are left out."""
        out: List[Tuple[str, Quote]] = []
        for code in codes:
            found = await self.quote_detail(code, base)
            if found is not None:
                out.append((code, found))
        return out
