"""The Telegram Bot API dialect, spoken by more than one provider.

Bale's bot API is the Telegram Bot API with a different host: the same methods,
the same update envelope, the same inline keyboards. Rather than keep two
copies of that in sync, the dialect lives here once and each provider supplies
what genuinely differs — the host, its own `Provider`, the deep-link format and
the header its webhooks are signed with.

This is a translation layer and nothing else. It never reads or writes a
financial table, and it never decides what anyone is allowed to do. An AST test
enforces that.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class UpdateBatch:
    """One poll's worth of updates, and how the attempt actually ended.

    Three outcomes, not two: updates arrived, the provider answered and refused,
    or nothing answered at all. The caller backs off differently for each, and
    collapsing the last two into "no updates" is how a bot spins silently
    against a revoked token.
    """

    updates: List[Dict[str, Any]] = field(default_factory=list)
    refused: Optional[str] = None
    unreachable: bool = False

    @property
    def ok(self) -> bool:
        return self.refused is None and not self.unreachable


class BotApiAdapter:
    """Everything that is identical between Telegram and Bale."""

    # Filled in by each provider.
    provider: Provider = Provider.TELEGRAM
    api_root: str = ""
    deep_link_template: str = ""
    secret_header: str = ""
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
        """The provider echoes the secret we registered; anything else is not it."""
        if not self.webhook_secret:
            return True  # no secret configured: nothing to check against
        if not self.secret_header:
            return True

        sent = headers.get(self.secret_header) or headers.get(
            self.secret_header.lower(), ""
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
            provider=self.provider,
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
            # Every size is sent; the last is the largest.
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
        return self.deep_link_template.format(username=self.bot_username, payload=payload)

    def _url(self, method: str) -> str:
        return f"{self.api_root}/bot{self.token}/{method}"

    async def _call(self, method: str, **params) -> Optional[Dict]:
        response = await self._client.post(self._url(method), json=params)
        body = response.json()
        if not body.get("ok"):
            return None
        return body.get("result")

    async def fetch_updates(
        self, offset: Optional[int] = None, timeout: int = 25
    ) -> UpdateBatch:
        """Long-poll for updates, reporting which of the three outcomes happened."""
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        try:
            response = await self._client.post(self._url("getUpdates"), json=params)
            body = response.json()
        except Exception as err:  # network, DNS, timeout, malformed body
            return UpdateBatch(unreachable=True, refused=str(err) or type(err).__name__)

        if not body.get("ok"):
            return UpdateBatch(refused=body.get("description") or "refused")
        return UpdateBatch(updates=body.get("result", []))

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
            self._url("sendDocument"),
            data=data,
            files={"document": (filename, content)},
        )
        body = response.json()
        return str(body["result"]["message_id"]) if body.get("ok") else None

    async def send_stored_file(self, chat_id: str, file_id: str) -> Optional[str]:
        """Forward a file the provider already has, by its id.

        Sending the id back is what keeps a receipt out of our storage entirely.
        A file id does not say whether it is a photo or a document, so the
        second call covers the case the first rejects.
        """
        for method in ("sendPhoto", "sendDocument"):
            field = "photo" if method == "sendPhoto" else "document"
            result = await self._call(method, **{"chat_id": chat_id, field: file_id})
            if result is not None:
                return str(result.get("message_id"))
        return None

    async def send_plain(self, chat_id: str, text: str) -> Optional[str]:
        """A message the bot starts, with no buttons and no screen to replace."""
        result = await self._call("sendMessage", chat_id=chat_id, text=text)
        return str(result.get("message_id")) if result else None

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

    async def delete_webhook(self) -> bool:
        """Polling and a webhook cannot both be active."""
        return bool(await self._call("deleteWebhook"))

    async def get_me(self) -> Optional[Dict]:
        """Who the token belongs to. Used at startup to prove it works."""
        return await self._call("getMe")

    async def aclose(self) -> None:
        await self._client.aclose()
