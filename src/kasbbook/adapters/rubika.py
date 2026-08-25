"""Rubika, through its official bot API at botapi.rubika.ir/v3.

Rubika is not a Telegram clone, so this is a real adapter rather than a subclass
of the shared dialect. Three differences drive everything here:

  * The envelope. Every response is `{"status": "OK", "data": {...}}` — there is
    no `ok` boolean and no `result`.
  * Buttons are not callbacks. A press arrives as an ordinary new message whose
    `aux_data.button_id` carries the payload, so there is no callback id to
    answer and nothing to keep spinning. `answer_callback` is a no-op that
    exists to satisfy the contract.
  * Keyboards are `inline_keypad` with rows of `{id, type, button_text}`, and
    the id is what comes back — so it, not a separate data field, is where the
    callback payload goes.

Only the published bot API is used. Rubika's web client can be observed and its
account API can be driven with a human login; neither belongs in a product.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import httpx

from ..modules.identity.models import Provider
from .base import (
    Attachment,
    Button,
    Capabilities,
    ChannelIdentity,
    EventKind,
    IncomingEvent,
    OutgoingMessage,
)
from .botapi import UpdateBatch

API_ROOT = "https://botapi.rubika.ir/v3"

__all__ = ["RubikaAdapter", "API_ROOT"]


class RubikaAdapter:
    """Rubika bot API adapter."""

    provider = Provider.RUBIKA

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

    def __init__(
        self,
        token: str,
        bot_username: str = "",
        webhook_secret: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.token = token
        self.bot_username = bot_username.lstrip("@")
        self.webhook_secret = webhook_secret
        self._client = client or httpx.AsyncClient(timeout=30)
        # Rubika pages with an opaque cursor rather than a numeric offset.
        self._next_offset: Optional[str] = None

    # ----------------------------------------------------------- inbound
    def verify_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """Rubika signs nothing, so this cannot prove the caller is Rubika.

        Saying so is the honest answer; the API mounts this provider's webhook
        behind a secret path instead of pretending to check a signature.
        """
        return True

    def parse_event(self, payload: Dict[str, Any]) -> Optional[IncomingEvent]:
        """One Rubika update in, one internal event out.

        Accepts either a bare update or the `{"update": {...}}` wrapper the
        webhook delivers, because both shapes reach this method.
        """
        update = payload.get("update") or payload
        message = update.get("new_message") or update.get("message")
        if not message:
            # Removed messages, message-update notices: nothing to act on.
            return None

        chat_id = str(update.get("chat_id") or message.get("chat_id") or "")
        sender_id = str(message.get("sender_id") or chat_id)
        message_id = str(message.get("message_id")) if message.get("message_id") else None
        text = message.get("text")

        identity = ChannelIdentity(
            provider=Provider.RUBIKA,
            external_id=sender_id,
            username=message.get("sender_username") or None,
            display_name=(update.get("sender_name") or message.get("sender_name")) or None,
        )

        aux = message.get("aux_data") or {}

        # A button press. It arrives as a message, but it is a callback in
        # everything that matters to the layer above, so it is presented as one.
        button_id = aux.get("button_id")
        if button_id:
            return IncomingEvent(
                kind=EventKind.CALLBACK,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                callback_data=str(button_id),
                # No callback id exists to answer. The field stays empty rather
                # than being filled with something the API would reject.
                callback_id=None,
                raw=update,
            )

        attachment = self._parse_attachment(message)
        if attachment is not None and not text:
            return IncomingEvent(
                kind=EventKind.ATTACHMENT,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                attachment=attachment,
                raw=update,
            )

        # A deep link. Rubika reports the payload in aux_data rather than in the
        # text, so /start arrives with its argument on the side.
        start_id = aux.get("start_id")
        if start_id:
            return IncomingEvent(
                kind=EventKind.COMMAND,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                command="start",
                args=str(start_id),
                raw=update,
            )

        if text and text.startswith("/"):
            head, _, rest = text.partition(" ")
            return IncomingEvent(
                kind=EventKind.COMMAND,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                command=head.split("@", 1)[0].lstrip("/"),
                args=rest.strip() or None,
                attachment=attachment,
                raw=update,
            )

        return IncomingEvent(
            kind=EventKind.MESSAGE,
            identity=identity,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            attachment=attachment,
            raw=update,
        )

    def _parse_attachment(self, message: Dict[str, Any]) -> Optional[Attachment]:
        file_info = message.get("file")
        if not file_info:
            return None

        name = file_info.get("file_name") or ""
        kind = "photo" if name.lower().endswith((".jpg", ".jpeg", ".png")) else "document"
        return Attachment(
            kind=kind,
            file_id=str(file_info.get("file_id", "")),
            file_name=name or None,
            mime_type=file_info.get("mime_type"),
        )

    def identify_user(self, event: IncomingEvent) -> ChannelIdentity:
        return event.identity

    # ---------------------------------------------------------- outbound
    def build_buttons(self, buttons: Sequence[Sequence[Button]]) -> Optional[Dict]:
        """Rows of `{id, type, button_text}`.

        The id is what Rubika hands back on a press, so the callback payload
        goes there. A url button is rendered as `Link`, and its target lives in
        `button_url` because there is no separate url field on a simple button.
        """
        if not buttons:
            return None

        rows: List[Dict[str, Any]] = []
        for row in buttons:
            rendered: List[Dict[str, Any]] = []
            for button in row:
                if button.url:
                    rendered.append({
                        "id": button.url,
                        "type": "Link",
                        "button_text": button.text,
                        "button_link": {"type": "url", "link_url": button.url},
                    })
                else:
                    rendered.append({
                        "id": button.data,
                        "type": "Simple",
                        "button_text": button.text,
                    })
            rows.append({"buttons": rendered})
        return {"rows": rows, "resize_keyboard": True}

    def create_deep_link(self, payload: str) -> str:
        if not self.bot_username:
            raise ValueError("a bot username is required to build a deep link")
        return f"https://rubika.ir/{self.bot_username}?start={payload}"

    def _url(self, method: str) -> str:
        return f"{API_ROOT}/{self.token}/{method}"

    async def _call(self, method: str, **params) -> Optional[Dict]:
        """Rubika answers `{"status": "OK", "data": {...}}`; anything else is a no."""
        response = await self._client.post(self._url(method), json=params)
        body = response.json()
        if str(body.get("status", "")).upper() != "OK":
            return None
        # A method with nothing to return still succeeded, so an empty data
        # object must not read as failure.
        return body.get("data") or {}

    async def fetch_updates(
        self, offset: Optional[int] = None, timeout: int = 25
    ) -> UpdateBatch:
        """Poll for updates.

        Rubika pages with an opaque `next_offset_id` string rather than a
        numeric offset, and does not long-poll, so `timeout` is accepted for
        contract compatibility and ignored.
        """
        params: Dict[str, Any] = {"limit": 100}
        if self._next_offset:
            params["offset_id"] = self._next_offset

        try:
            response = await self._client.post(self._url("getUpdates"), json=params)
            body = response.json()
        except Exception as err:
            return UpdateBatch(unreachable=True, refused=str(err) or type(err).__name__)

        if str(body.get("status", "")).upper() != "OK":
            return UpdateBatch(refused=body.get("status") or "refused")

        data = body.get("data") or {}
        self._next_offset = data.get("next_offset_id") or self._next_offset
        return UpdateBatch(updates=data.get("updates", []))

    async def send_message(self, message: OutgoingMessage) -> Optional[str]:
        params: Dict[str, Any] = {"chat_id": message.chat_id, "text": message.text}
        keypad = self.build_buttons(message.buttons)
        if keypad:
            params["inline_keypad"] = keypad

        result = await self._call("sendMessage", **params)
        return str(result.get("message_id")) if result else None

    async def edit_message(self, message: OutgoingMessage) -> Optional[str]:
        if not message.edit_message_id:
            return await self.send_message(message)

        result = await self._call(
            "editMessageText",
            chat_id=message.chat_id,
            message_id=message.edit_message_id,
            text=message.text,
        )
        if result is None:
            return await self.send_message(
                OutgoingMessage(message.chat_id, message.text, message.buttons)
            )

        # Editing text does not touch the keyboard, so the buttons are replaced
        # separately or the screen keeps the previous screen's buttons.
        keypad = self.build_buttons(message.buttons)
        if keypad:
            await self._call(
                "editMessageKeypad",
                chat_id=message.chat_id,
                message_id=message.edit_message_id,
                inline_keypad=keypad,
            )
        return str(message.edit_message_id)

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        return (
            await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)
            is not None
        )

    async def send_file(
        self, chat_id: str, content: bytes, filename: str, caption: Optional[str] = None
    ) -> Optional[str]:
        """Rubika uploads in two steps: ask for a URL, then post the bytes to it."""
        target = await self._call("requestSendFile", type="File")
        upload_url = (target or {}).get("upload_url")
        if not upload_url:
            return None

        response = await self._client.post(
            upload_url, files={"file": (filename, content)}
        )
        body = response.json()
        file_id = ((body.get("data") or {}).get("file_id")) if body else None
        if not file_id:
            return None

        params: Dict[str, Any] = {
            "chat_id": chat_id, "file_id": file_id, "file_name": filename,
        }
        if caption:
            params["text"] = caption
        result = await self._call("sendFile", **params)
        return str(result.get("message_id")) if result else None

    async def send_stored_file(self, chat_id: str, file_id: str) -> Optional[str]:
        result = await self._call("sendFile", chat_id=chat_id, file_id=file_id)
        return str(result.get("message_id")) if result else None

    async def send_plain(self, chat_id: str, text: str) -> Optional[str]:
        result = await self._call("sendMessage", chat_id=chat_id, text=text)
        return str(result.get("message_id")) if result else None

    async def answer_callback(self, callback_id: str, text: Optional[str] = None) -> None:
        """Nothing to answer.

        A Rubika button press is a message, not a callback, so no spinner is
        waiting on a reply. This exists so the layer above can call it on every
        provider without asking which one it is talking to.
        """
        return None

    async def set_webhook(self, url: str) -> bool:
        return await self._call("updateBotEndpoints", url=url, type="ReceiveUpdate") is not None

    async def delete_webhook(self) -> bool:
        return await self._call("updateBotEndpoints", url="", type="ReceiveUpdate") is not None

    async def get_me(self) -> Optional[Dict]:
        return await self._call("getMe")

    async def aclose(self) -> None:
        await self._client.aclose()
