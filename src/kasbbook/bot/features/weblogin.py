"""Approving a browser that asked to sign in.

The website shows a link into the bot; opening it lands here. The person is
shown what asked and decides — a link alone never signs anyone in, because a
link can be sent to somebody else.
"""

from __future__ import annotations

from ...modules.identity.weblogin import WebLoginService
from .. import screens
from .base import Feature


class WebLoginFeature(Feature):
    prefixes = ("wl",)

    async def prompt(self, token: str, user):
        row = await WebLoginService(self.ctx.session).describe(token)
        return screens.web_login_prompt(token, row.requester_ip or "", row.requester_agent or "")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        token = parts[2] if len(parts) > 2 else ""
        service = WebLoginService(self.ctx.session)
        if action == "ok":
            await service.approve(token, user.id)
            return screens.web_login_done()
        if action == "no":
            await service.deny(token, user.id)
            return screens.web_login_refused()
        return screens.stale(None, user.display_name)
