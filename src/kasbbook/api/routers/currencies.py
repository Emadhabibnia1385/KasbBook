"""The catalog of currencies a book can hold or be kept in, for the web's picker."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from ...modules.exchange.catalog import CATALOG, POPULAR
from ..deps import CurrentUser
from ..schemas import CatalogCurrencyResponse

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=List[CatalogCurrencyResponse])
async def catalog(user: CurrentUser) -> List[CatalogCurrencyResponse]:
    """Every currency KasbBook knows: crypto and the legal tender of every country.

    The same for everyone, so it needs a sign-in but no book. Static data: a
    client may keep it for a long time.
    """
    return [
        CatalogCurrencyResponse(code=c.code, name=c.name, symbol=c.symbol, kind=c.kind,
                                region=c.region, popular=c.code in POPULAR)
        for c in CATALOG
    ]
