"""The person's own account in the bot: profile, password, messengers, API key, sessions.

The only feature that is about the person rather than a book, so it is the only
one that is never asked which book it is acting on.
"""

from __future__ import annotations

import uuid

from ...adapters.base import OutgoingMessage
from ...shared.errors import KasbBookError
from ...shared.parsing import to_ascii_digits
from .. import screens
from .base import Feature


class AccountFeature(Feature):
    prefixes = ("acc",)
    flows = ("account", "account_login")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "acc":
            return await self._account_callback(action, argument, user, key, event)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "account":
            return await self._account_text(text, draft, user, key)
        if draft.get("flow") == "account_login":
            return await self._account_login_text(text, draft, user, key, event)
        raise AssertionError(draft.get("flow"))

    # ------------------------------------------------------------- account
    async def _account_panel(self, user):
        return screens.account_panel(
            user, await self.ctx.identity.list_identities(user.id), self.ctx.provider
        )

    async def _account_callback(self, action: str, argument: str, user, key: str, event):
        if action == "create":
            return screens.account_created(user.display_name)
        if action == "login":
            await self.ctx.state.set(key, {"flow": "account_login", "awaiting": "destination"})
            return screens.ask_login_destination()
        if action == "newcode":
            issued = await self.ctx.identity.start_link_from_messenger(
                self.ctx.provider, event.identity.external_id
            )
            return screens.not_linked(issued.token)

        if action == "list":
            await self.ctx.state.clear(key)
            return screens.identity_list(
                await self.ctx.identity.list_identities(user.id), self.ctx.provider
            )

        if action in ("panel", "contact"):
            await self.ctx.state.clear(key)
            return await self._account_panel(user)

        if action == "name":
            await self.ctx.state.set(key, {"flow": "account", "field": "name"})
            return screens.ask_display_name(user.display_name)

        if action == "email":
            await self.ctx.state.set(key, {"flow": "account", "field": "email"})
            return screens.ask_email()

        if action == "phone":
            await self.ctx.state.set(key, {"flow": "account", "field": "phone"})
            return screens.ask_phone()

        if action == "tz":
            return screens.ask_timezone(user.timezone)

        if action == "tzset":
            # The zone name contains a slash, which the splitter took for a
            # separator; rebuild it from what is left of the callback.
            zone = ":".join((event.callback_data or "").split(":")[2:])
            await self.ctx.identity.update_profile(user.id, timezone=zone)
            return await self._account_panel(user)

        if action == "pw":
            # Asking for the current one first only makes sense when there is
            # one; a new account is setting its first password.
            field = "password_current" if user.password_hash else "password_new"
            await self.ctx.state.set(key, {"flow": "account", "field": field})
            return (
                screens.ask_current_password() if user.password_hash
                else screens.ask_new_password(changing=False)
            )

        if action == "close":
            await self.ctx.state.clear(key)
            return screens.confirm_close(
                await self.ctx.identity.deletion_preview(user.id)
            )

        if action == "closeok":
            preview = await self.ctx.identity.deletion_preview(user.id)
            if preview.blocked:
                # It could have become blocked between the two screens.
                return screens.confirm_close(preview)

            await self.ctx.state.set(key, {"flow": "account", "field": "close"})
            return screens.ask_close_word()

        if action == "api":
            await self.ctx.state.clear(key)
            return screens.api_panel(
                await self._auth().list_api_keys(user.id),
                self._docs_url(),
                self._guide_url(),
            )

        if action == "apinew":
            auth = self._auth()
            existing = await auth.list_api_keys(user.id)
            # One key per person: a second one nobody remembers issuing is a
            # credential nobody will think to revoke.
            for old in existing:
                await auth.revoke_api_key(user.id, old.id)

            issued = await auth.issue_api_key(user.id, "bot")
            self.ctx.hidden = issued.key
            return screens.api_key_created(
                issued.key,
                replaced=bool(existing),
                docs_url=self._docs_url(),
                guide_url=self._guide_url(),
            )

        if action == "sessions":
            return screens.session_list(await self._auth().sessions(user.id))

        if action == "signout":
            await self._auth().revoke_all_for_user(user.id)
            return screens.session_list([])

        return await self._account_panel(user)

    def _docs_url(self) -> str:
        """Where this deployment's own API reference lives, if it is published."""
        from ...shared.settings import Settings

        return Settings.from_env().api_base_url

    def _guide_url(self) -> str:
        """Where the written guide lives — the software's, not this instance's."""
        from ...shared.settings import Settings

        return Settings.from_env().docs_url

    def _auth(self):
        """Sessions live behind AuthService, which needs the signing key.

        The bot never mints a token, so any key satisfies the constructor —
        but passing a real one keeps this honest if that ever changes.
        """
        from ...modules.identity.auth import AuthService
        from ...shared.settings import Settings

        return AuthService(self.ctx.session, Settings.from_env().api_secret_key or "bot")

    async def _account_text(self, text: str, draft: dict, user, key: str):
        field = draft.get("field")

        try:
            if field == "name":
                await self.ctx.identity.update_profile(user.id, display_name=text)
            elif field == "email":
                await self.ctx.identity.set_contact(user.id, email=text)
            elif field == "phone":
                await self.ctx.identity.set_contact(user.id, phone=text)
            elif field == "password_current":
                # Held only long enough to prove the next one is allowed.
                draft["current"] = text
                draft["field"] = "password_new"
                await self.ctx.state.set(key, draft)
                return screens.ask_new_password(changing=True)
            elif field == "close":
                if text.strip() != screens.CLOSE_WORD:
                    await self.ctx.state.clear(key)
                    return await self._account_panel(user)

                removed = await self.ctx.identity.delete_account(user.id)
                await self.ctx.state.clear(key)
                # Nothing below may touch `user` again: the row is either gone
                # or stripped of everything that identified it.
                return screens.account_closed(removed)
            elif field == "password_new":
                await self.ctx.identity.set_password(
                    user.id, text, current_password=draft.get("current")
                )
                # A password change signs every other session out. Someone who
                # changes it because they fear it leaked expects exactly that.
                await self._auth().revoke_all_for_user(user.id)
            else:
                await self.ctx.state.clear(key)
                return await self._account_panel(user)
        except KasbBookError as exc:
            # Stay in the flow so the answer can be corrected without starting
            # again, except for a wrong current password, which starts over.
            if field == "password_new" and draft.get("current"):
                await self.ctx.state.clear(key)
                return screens.error(screens.user_message(exc))
            return screens.error(screens.user_message(exc))

        await self.ctx.state.clear(key)
        return await self._account_panel(user)

    async def _account_login_text(self, text: str, draft: dict, user, key: str, event):
        identity = await self.ctx.identity.find_identity(self.ctx.provider, event.identity.external_id)
        if draft.get("awaiting") == "destination":
            issued = await self.ctx.account_login.request(user.id, identity.id, to_ascii_digits(text))
            await self.ctx.state.set(key, {"flow": "account_login", "awaiting": "code",
                                      "challenge_id": str(issued.challenge_id)})
            if issued.destination_external_id:
                proof, buttons = screens.login_proof(issued.code)
                self.ctx.notifications.append(OutgoingMessage(issued.destination_external_id, proof, buttons))
            return screens.ask_login_code()
        target = await self.ctx.account_login.complete(user.id, identity.id,
            uuid.UUID(draft["challenge_id"]), to_ascii_digits(text))
        if target is None:
            return screens.error("کد معتبر نیست یا منقضی شده است.")
        await self.ctx.state.clear(key)
        return screens.welcome(target.display_name)
