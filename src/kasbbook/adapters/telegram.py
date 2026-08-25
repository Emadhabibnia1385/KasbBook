"""Telegram, spoken through the shared adapter contract.

Uses the official Bot API and nothing else. The HTTP client is injected so the
test suite exercises every parse and every outgoing call without touching the
network — which is also what lets the same tests run in CI.
"""

from __future__ import annotations

import hmac
from typing import Any, Dict, Optional, Sequence

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

API_ROOT = "https://api.telegram.org"


class TelegramAdapter:
    """Telegram Bot API adapter.

    Telegram supports everything in `Capabilities`, which makes it the reference
    implementation the others are compared against.
    """

    provider = Provider.TELEGRAM
    capabilities = Capabilities()

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

    # ----------------------------------------------------------- inbound
    def verify_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """Telegram echoes the secret we registered; anything else is not it."""
        if not self.webhook_secret:
            return True  # no secret configured: nothing to check against

        sent = headers.get("X-Telegram-Bot-Api-Secret-Token") or headers.get(
            "x-telegram-bot-api-secret-token", ""
        )
        return hmac.compare_digest(sent, self.webhook_secret)

    def parse_event(self, payload: Dict[str, Any]) -> Optional[IncomingEvent]:
        if "callback_query" in payload:
            return self._parse_callback(payload["callback_query"])

        message = payload.get("message") or payload.get("edited_message")
        if message:
            return self._parse_message(message)

        # Channel posts, polls, member updates: nothing this bot acts on.
        return None

    def _identity(self, sender: Dict[str, Any]) -> ChannelIdentity:
        name = " ".join(
            part for part in (sender.get("first_name"), sender.get("last_name")) if part
        )
        return ChannelIdentity(
            provider=Provider.TELEGRAM,
            external_id=str(sender.get("id", "")),
            username=sender.get("username"),
            display_name=name or None,
        )

    def _parse_callback(self, callback: Dict[str, Any]) -> IncomingEvent:
        message = callback.get("message") or {}
        return IncomingEvent(
            kind=EventKind.CALLBACK,
            identity=self._identity(callback.get("from") or {}),
            chat_id=str((message.get("chat") or {}).get("id", "")),
            message_id=str(message["message_id"]) if message.get("message_id") else None,
            callback_data=callback.get("data"),
            callback_id=str(callback.get("id", "")),
            raw=callback,
        )

    def _parse_message(self, message: Dict[str, Any]) -> IncomingEvent:
        identity = self._identity(message.get("from") or {})
        chat_id = str((message.get("chat") or {}).get("id", ""))
        message_id = str(message["message_id"]) if message.get("message_id") else None
        text = message.get("text") or message.get("caption")

        attachment = self._parse_attachment(message)
        if attachment is not None and not text:
            return IncomingEvent(
                kind=EventKind.ATTACHMENT,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                attachment=attachment,
                raw=message,
            )

        if text and text.startswith("/"):
            head, _, rest = text.partition(" ")
            # "/start@KasbBook_BOT" in groups — the mention is not part of the command.
            command = head.split("@", 1)[0].lstrip("/")
            return IncomingEvent(
                kind=EventKind.COMMAND,
                identity=identity,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                command=command,
                args=rest.strip() or None,
                attachment=attachment,
                raw=message,
            )

        return IncomingEvent(
            kind=EventKind.MESSAGE,
            identity=identity,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            attachment=attachment,
            raw=message,
        )

    def _parse_attachment(self, message: Dict[str, Any]) -> Optional[Attachment]:
        photos = message.get("photo")
        if photos:
            # Telegram sends every size; the last is the largest.
            return Attachment(kind="photo", file_id=photos[-1]["file_id"])

        document = message.get("document")
        if document:
            return Attachment(
                kind="document",
                file_id=document["file_id"],
                file_name=document.get("file_name"),
                mime_type=document.get("mime_type"),
            )

        voice = message.get("voice")
        if voice:
            return Attachment(kind="voice", file_id=voice["file_id"])
        return None

    def identify_user(self, event: IncomingEvent) -> ChannelIdentity:
        return event.identity

    # ---------------------------------------------------------- outbound
    def build_buttons(self, buttons: Sequence[Sequence[Button]]) -> Optional[Dict]:
        if not buttons:
            return None

        rows = []
        for row in buttons:
            rendered = []
            for button in row:
                if button.url:
                    rendered.append({"text": button.text, "url": button.url})
                else:
                    rendered.append({"text": button.text, "callback_data": button.data})
            rows.append(rendered)
        return {"inline_keyboard": rows}

    def create_deep_link(self, payload: str) -> str:
        if not self.bot_username:
            raise ValueError("a bot username is required to build a deep link")
        return f"https://t.me/{self.bot_username}?start={payload}"

    async def _call(self, method: str, **params) -> Optional[Dict]:
        response = await self._client.post(
            f"{API_ROOT}/bot{self.token}/{method}", json=params
        )
        body = response.json()
        if not body.get("ok"):
            return None
        return body.get("result")

    async def send_message(self, message: OutgoingMessage) -> Optional[str]:
        params: Dict[str, Any] = {"chat_id": message.chat_id, "text": message.text}
        markup = self.build_buttons(message.buttons)
        if markup:
            params["reply_markup"] = markup

        result = await self._call("sendMessage", **params)
        return str(result["message_id"]) if result else None

    async def edit_message(self, message: OutgoingMessage) -> Optional[str]:
        if not message.edit_message_id:
            return await self.send_message(message)

        params: Dict[str, Any] = {
            "chat_id": message.chat_id,
            "message_id": int(message.edit_message_id),
            "text": message.text,
        }
        markup = self.build_buttons(message.buttons)
        if markup:
            params["reply_markup"] = markup

        result = await self._call("editMessageText", **params)
        if result is None:
            # The anchor is gone or unchanged; a fresh message is the safe fallback.
            return await self.send_message(
                OutgoingMessage(message.chat_id, message.text, message.buttons)
            )
        return str(result["message_id"])

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        return bool(
            await self._call("deleteMessage", chat_id=chat_id, message_id=int(message_id))
        )

    async def send_file(
        self, chat_id: str, content: bytes, filename: str, caption: Optional[str] = None
    ) -> Optional[str]:
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption

        response = await self._client.post(
            f"{API_ROOT}/bot{self.token}/sendDocument",
            data=data,
            files={"document": (filename, content)},
        )
        body = response.json()
        return str(body["result"]["message_id"]) if body.get("ok") else None

    async def answer_callback(self, callback_id: str, text: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            params["text"] = text
        await self._call("answerCallbackQuery", **params)

    async def set_webhook(self, url: str) -> bool:
        params: Dict[str, Any] = {"url": url}
        if self.webhook_secret:
            params["secret_token"] = self.webhook_secret
        return bool(await self._call("setWebhook", **params))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_stored_file(self, chat_id: str, file_id: str) -> Optional[str]:
        """Forward a file Telegram already has, by its id.

        Sending the id back is what keeps a receipt out of our storage entirely.
        A file id can belong to a photo or a document, and Telegram will not say
        which, so the second call covers the case the first rejects.
        """
        for method in ("sendPhoto", "sendDocument"):
            field = "photo" if method == "sendPhoto" else "document"
            result = await self._call(method, {"chat_id": chat_id, field: file_id})
            if result is not None:
                return str(result.get("message_id"))
        return None

    async def send_plain(self, chat_id: str, text: str) -> Optional[str]:
        """A message the bot starts, with no buttons and no screen to replace."""
        result = await self._call("sendMessage", {"chat_id": chat_id, "text": text})
        return str(result.get("message_id")) if result else None

