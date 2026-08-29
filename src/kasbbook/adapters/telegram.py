"""Telegram, spoken through the shared adapter contract.

The official Bot API and nothing else — no reverse-engineered client API, no
logging in as a human. Almost all of the implementation is the Bot API dialect
in `botapi.py`, which Bale speaks too; what is left here is what is genuinely
Telegram's own.

The HTTP client is injected so the test suite exercises every parse and every
outgoing call without touching the network — which is also what lets the same
tests run in CI.
"""

from __future__ import annotations

from ..modules.identity.models import Provider
from .base import Capabilities
from .botapi import BotApiAdapter, UpdateBatch

API_ROOT = "https://api.telegram.org"

__all__ = ["TelegramAdapter", "UpdateBatch", "API_ROOT"]


class TelegramAdapter(BotApiAdapter):
    """Telegram Bot API adapter.

    Telegram supports everything in `Capabilities`, which makes it the reference
    implementation the others are compared against.
    """

    provider = Provider.TELEGRAM
    api_root = API_ROOT
    deep_link_template = "https://t.me/{username}?start={payload}"
    secret_header = "X-Telegram-Bot-Api-Secret-Token"
    capabilities = Capabilities(spoiler=True)
