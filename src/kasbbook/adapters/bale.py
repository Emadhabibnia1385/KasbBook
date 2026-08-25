"""Bale, through its official bot API.

Bale publishes a Bot API that is the Telegram Bot API with a different host:
the same method names, the same update envelope, the same inline keyboards. So
this adapter is the shared dialect plus four facts, and every behaviour it
inherits is covered by the same tests that cover Telegram.

Only the official API is used. Bale also has a web client whose endpoints can be
observed, and an account login that issues an OTP to a real phone number; both
are out of bounds here. A bot posts as a bot.
"""

from __future__ import annotations

from ..modules.identity.models import Provider
from .base import Capabilities
from .botapi import BotApiAdapter

API_ROOT = "https://tapi.bale.ai"

__all__ = ["BaleAdapter", "API_ROOT"]


class BaleAdapter(BotApiAdapter):
    """Bale Bot API adapter."""

    provider = Provider.BALE
    api_root = API_ROOT
    deep_link_template = "https://ble.ir/{username}?start={payload}"

    # Bale does not document a secret-token header on its webhooks the way
    # Telegram does. Rather than pretend to verify, the webhook route requires
    # an unguessable path for Bale — see `verify_webhook` below.
    secret_header = ""

    capabilities = Capabilities(
        inline_buttons=True,
        edit_message=True,
        delete_message=True,
        send_file=True,
        receive_file=True,
        deep_link=True,
        webhook=True,
        polling=True,
    )

    def verify_webhook(self, headers, body) -> bool:
        """Bale sends no signature, so there is nothing here to verify.

        Returning True is honest — this adapter cannot prove the caller is Bale.
        The proof has to come from somewhere else, which is why the API mounts
        Bale's webhook on a path containing a secret and refuses the request
        when that path does not match. Claiming a check that does not exist
        would be worse than admitting there is none.
        """
        return True
