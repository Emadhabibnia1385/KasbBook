"""The Telegram adapter, exercised without a network.

Every outgoing call is captured by a mock transport, so these tests prove the
parsing and the request shapes without a token, without the internet, and
identically in CI.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

from kasbbook.adapters.base import Button, EventKind, OutgoingMessage
from kasbbook.adapters.telegram import TelegramAdapter
from kasbbook.modules.identity.models import Provider

pytestmark = pytest.mark.asyncio


class FakeTelegram:
    """Records what the adapter sent and replies the way Telegram would."""

    def __init__(self, ok: bool = True, message_id: int = 42) -> None:
        self.ok = ok
        self.message_id = message_id
        self.calls: List[Dict[str, Any]] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            method = request.url.path.rsplit("/", 1)[-1]
            try:
                body = json.loads(request.content) if request.content else {}
            except (ValueError, UnicodeDecodeError):
                body = {"_multipart": True}

            self.calls.append({"method": method, "body": body})
            if not self.ok:
                return httpx.Response(200, json={"ok": False, "description": "nope"})
            return httpx.Response(
                200, json={"ok": True, "result": {"message_id": self.message_id}}
            )

        return httpx.MockTransport(handle)

    def adapter(self, **kwargs) -> TelegramAdapter:
        client = httpx.AsyncClient(transport=self.transport())
        return TelegramAdapter(token="test-token", client=client, **kwargs)

    def last(self) -> Dict[str, Any]:
        return self.calls[-1]


# ------------------------------------------------------------------ parsing
async def test_a_plain_message_becomes_a_message_event():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 7,
                "from": {"id": 555001, "username": "emad", "first_name": "عماد"},
                "chat": {"id": 555001},
                "text": "فروش 250000",
            }
        }
    )

    assert event.kind is EventKind.MESSAGE
    assert event.text == "فروش 250000"
    assert event.chat_id == "555001"
    assert event.message_id == "7"
    assert event.identity.provider is Provider.TELEGRAM
    assert event.identity.external_id == "555001"
    assert event.identity.username == "emad"
    assert event.identity.display_name == "عماد"


async def test_a_command_is_split_from_its_arguments():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 1,
                "from": {"id": 1},
                "chat": {"id": 1},
                "text": "/start LINKTOKEN123",
            }
        }
    )

    assert event.kind is EventKind.COMMAND
    assert event.command == "start"
    assert event.args == "LINKTOKEN123"


async def test_a_group_mention_is_not_part_of_the_command():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 1,
                "from": {"id": 1},
                "chat": {"id": -100},
                "text": "/start@KasbBook_BOT abc",
            }
        }
    )

    assert event.command == "start"
    assert event.args == "abc"


async def test_a_command_without_arguments_has_none():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {"message": {"message_id": 1, "from": {"id": 1}, "chat": {"id": 1}, "text": "/cancel"}}
    )

    assert event.command == "cancel"
    assert event.args is None


async def test_a_button_press_becomes_a_callback_event():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "callback_query": {
                "id": "cb-1",
                "from": {"id": 555001},
                "data": "book:pick:abc",
                "message": {"message_id": 9, "chat": {"id": 555001}},
            }
        }
    )

    assert event.kind is EventKind.CALLBACK
    assert event.callback_data == "book:pick:abc"
    assert event.callback_id == "cb-1"
    assert event.message_id == "9"


async def test_the_largest_photo_size_is_the_one_kept():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 3,
                "from": {"id": 1},
                "chat": {"id": 1},
                "photo": [
                    {"file_id": "small", "width": 90},
                    {"file_id": "large", "width": 1280},
                ],
            }
        }
    )

    assert event.kind is EventKind.ATTACHMENT
    assert event.attachment.kind == "photo"
    assert event.attachment.file_id == "large"


async def test_a_document_keeps_its_name_and_type():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 3,
                "from": {"id": 1},
                "chat": {"id": 1},
                "document": {
                    "file_id": "doc-1",
                    "file_name": "receipt.pdf",
                    "mime_type": "application/pdf",
                },
            }
        }
    )

    assert event.attachment.file_name == "receipt.pdf"
    assert event.attachment.mime_type == "application/pdf"


async def test_a_captioned_photo_keeps_both_the_caption_and_the_file():
    adapter = FakeTelegram().adapter()
    event = adapter.parse_event(
        {
            "message": {
                "message_id": 3,
                "from": {"id": 1},
                "chat": {"id": 1},
                "photo": [{"file_id": "p1"}],
                "caption": "رسید اجاره",
            }
        }
    )

    assert event.kind is EventKind.MESSAGE
    assert event.text == "رسید اجاره"
    assert event.attachment.file_id == "p1"


async def test_updates_the_bot_does_not_act_on_are_ignored():
    adapter = FakeTelegram().adapter()
    for payload in (
        {"channel_post": {"message_id": 1}},
        {"poll": {"id": "p"}},
        {"my_chat_member": {}},
        {},
    ):
        assert adapter.parse_event(payload) is None


# ------------------------------------------------------------- webhook auth
async def test_a_webhook_without_the_secret_is_rejected():
    adapter = FakeTelegram().adapter(webhook_secret="s3cret")

    assert adapter.verify_webhook({"X-Telegram-Bot-Api-Secret-Token": "s3cret"}, b"")
    assert not adapter.verify_webhook({"X-Telegram-Bot-Api-Secret-Token": "wrong"}, b"")
    assert not adapter.verify_webhook({}, b"")


async def test_the_header_is_matched_case_insensitively():
    adapter = FakeTelegram().adapter(webhook_secret="s3cret")
    assert adapter.verify_webhook({"x-telegram-bot-api-secret-token": "s3cret"}, b"")


async def test_with_no_secret_configured_nothing_is_claimed():
    adapter = FakeTelegram().adapter()
    assert adapter.verify_webhook({}, b"") is True


# ---------------------------------------------------------------- outbound
async def test_sending_a_message_hits_sendMessage_with_the_text():
    fake = FakeTelegram()
    adapter = fake.adapter()

    message_id = await adapter.send_message(
        OutgoingMessage(chat_id="555001", text="سلام")
    )

    assert message_id == "42"
    assert fake.last()["method"] == "sendMessage"
    assert fake.last()["body"]["chat_id"] == "555001"
    assert fake.last()["body"]["text"] == "سلام"


async def test_buttons_render_as_a_telegram_inline_keyboard():
    fake = FakeTelegram()
    adapter = fake.adapter()

    await adapter.send_message(
        OutgoingMessage(
            chat_id="1",
            text="کدام دفتر؟",
            buttons=[
                [Button("شخصی", data="book:personal")],
                [Button("راهنما", url="https://example.com")],
            ],
        )
    )

    markup = fake.last()["body"]["reply_markup"]["inline_keyboard"]
    assert markup[0][0] == {"text": "شخصی", "callback_data": "book:personal"}
    assert markup[1][0] == {"text": "راهنما", "url": "https://example.com"}


async def test_a_message_without_buttons_sends_no_markup():
    fake = FakeTelegram()
    adapter = fake.adapter()
    await adapter.send_message(OutgoingMessage(chat_id="1", text="x"))
    assert "reply_markup" not in fake.last()["body"]


async def test_a_button_must_carry_either_data_or_a_url():
    with pytest.raises(ValueError):
        Button("بی‌کار")


async def test_editing_uses_editMessageText():
    fake = FakeTelegram()
    adapter = fake.adapter()

    await adapter.edit_message(
        OutgoingMessage(chat_id="1", text="به‌روز", edit_message_id="9")
    )

    assert fake.last()["method"] == "editMessageText"
    assert fake.last()["body"]["message_id"] == 9


async def test_editing_without_an_anchor_sends_a_new_message():
    fake = FakeTelegram()
    adapter = fake.adapter()

    await adapter.edit_message(OutgoingMessage(chat_id="1", text="تازه"))
    assert fake.last()["method"] == "sendMessage"


async def test_a_failed_edit_falls_back_to_a_fresh_message():
    """The anchor may have been deleted; the user still needs to see the screen."""
    fake = FakeTelegram(ok=False)
    adapter = fake.adapter()

    await adapter.edit_message(
        OutgoingMessage(chat_id="1", text="متن", edit_message_id="9")
    )

    assert [c["method"] for c in fake.calls] == ["editMessageText", "sendMessage"]


async def test_answering_a_callback_stops_the_button_spinning():
    fake = FakeTelegram()
    adapter = fake.adapter()

    await adapter.answer_callback("cb-1", "انجام شد")
    assert fake.last()["method"] == "answerCallbackQuery"
    assert fake.last()["body"]["callback_query_id"] == "cb-1"


async def test_sending_a_file_uses_multipart_not_json():
    fake = FakeTelegram()
    adapter = fake.adapter()

    await adapter.send_file("1", b"col1,col2\n", "report.csv", caption="گزارش")
    assert fake.last()["method"] == "sendDocument"
    assert fake.last()["body"] == {"_multipart": True}


async def test_deleting_a_message_calls_deleteMessage():
    fake = FakeTelegram()
    adapter = fake.adapter()

    assert await adapter.delete_message("1", "9") is True
    assert fake.last()["method"] == "deleteMessage"


async def test_the_webhook_registers_the_secret_alongside_the_url():
    fake = FakeTelegram()
    adapter = fake.adapter(webhook_secret="s3cret")

    await adapter.set_webhook("https://example.com/tg")
    assert fake.last()["method"] == "setWebhook"
    assert fake.last()["body"]["secret_token"] == "s3cret"


# -------------------------------------------------------------- deep links
async def test_a_deep_link_carries_the_payload_to_the_bot():
    adapter = FakeTelegram().adapter(bot_username="@KasbBook_BOT")
    assert adapter.create_deep_link("ABC123") == "https://t.me/KasbBook_BOT?start=ABC123"


async def test_a_deep_link_needs_a_bot_username():
    adapter = FakeTelegram().adapter()
    with pytest.raises(ValueError):
        adapter.create_deep_link("ABC123")


# ------------------------------------------------------------ capabilities
async def test_telegram_declares_every_capability():
    adapter = FakeTelegram().adapter()
    caps = adapter.capabilities

    assert caps.inline_buttons and caps.edit_message and caps.delete_message
    assert caps.send_file and caps.receive_file and caps.deep_link
    assert caps.webhook and caps.polling


async def test_the_adapter_never_reaches_the_database():
    """An adapter translates payloads. Nothing more — by construction.

    Checked through the import graph rather than by searching the text, so a
    comment mentioning a model name cannot fail the build and a real import
    cannot hide inside a string.
    """
    import ast
    import pathlib

    folder = pathlib.Path(__file__).resolve().parents[2] / "src/kasbbook/adapters"
    modules = sorted(p for p in folder.glob("*.py") if p.name != "__init__.py")
    assert len(modules) >= 4, "every adapter module has to be checked, not just one"

    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(f"{node.module or ''}.{a.name}" for a in node.names)

        banned = ("sqlalchemy", "shared.database", "modules.books", "modules.ledger",
                  ".service")
        leaked = [name for name in imported for bad in banned if bad in name]
        assert not leaked, f"{module.name} imports persistence: {leaked}"


# ------------------------------------------- every outgoing call, really made
#
# `send_plain` and `send_stored_file` both passed their parameters to `_call`
# as a positional dict where it takes keyword arguments. Both raised TypeError
# on the first line of the body, and both shipped: the reminder tests use a spy
# adapter, and the receipt tests assert on the reply object without ever
# handing it to Telegram. So the two methods nothing else covered were exactly
# the two that were broken.
#
# The table below is checked against the class itself, so a new outgoing method
# cannot be added without a case here.

CALLS = {
    "send_message": lambda a: a.send_message(OutgoingMessage("1", "سلام")),
    "edit_message": lambda a: a.edit_message(
        OutgoingMessage("1", "سلام", edit_message_id="9")
    ),
    "delete_message": lambda a: a.delete_message("1", "9"),
    "send_file": lambda a: a.send_file("1", b"data", "export.csv"),
    "send_plain": lambda a: a.send_plain("1", "خلاصهٔ امروز"),
    "send_stored_file": lambda a: a.send_stored_file("1", "PHOTO-1", "photo"),
    "answer_callback": lambda a: a.answer_callback("cb1"),
    "set_webhook": lambda a: a.set_webhook("https://example.test/hook"),
    "delete_webhook": lambda a: a.delete_webhook(),
    "get_me": lambda a: a.get_me(),
    "fetch_updates": lambda a: a.fetch_updates(offset=1, timeout=0),
    "aclose": lambda a: a.aclose(),
}


@pytest.mark.parametrize("name", sorted(CALLS))
async def test_every_outgoing_method_survives_a_real_call(name):
    fake = FakeTelegram()
    await CALLS[name](fake.adapter())


async def test_a_digest_reaches_telegram_as_a_plain_message():
    """The reminder loop's only way to speak. It was raising TypeError."""
    fake = FakeTelegram()
    assert await fake.adapter().send_plain("555", "خلاصهٔ امروز") == "42"

    assert fake.calls[0]["method"] == "sendMessage"
    assert fake.calls[0]["body"] == {"chat_id": "555", "text": "خلاصهٔ امروز"}


async def test_a_receipt_is_forwarded_by_id_not_re_uploaded():
    fake = FakeTelegram()
    assert await fake.adapter().send_stored_file("555", "PHOTO-1") == "42"

    assert fake.calls[0]["method"] == "sendPhoto"
    assert fake.calls[0]["body"] == {"chat_id": "555", "photo": "PHOTO-1"}


async def test_a_known_document_goes_straight_to_senddocument():
    """The reason the kind is recorded at all.

    Without it every PDF invoice cost a rejected sendPhoto before reaching
    sendDocument — a wasted round trip on every view, forever.
    """
    fake = FakeTelegram()
    assert await fake.adapter().send_stored_file("555", "DOC-1", "document") == "42"

    assert [c["method"] for c in fake.calls] == ["sendDocument"]
    assert fake.calls[0]["body"] == {"chat_id": "555", "document": "DOC-1"}


async def test_a_receipt_telegram_calls_a_document_still_arrives():
    """A file id does not say what it is, so the second attempt covers the first."""
    calls: List[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        if method == "sendPhoto":
            return httpx.Response(200, json={"ok": False, "description": "wrong type"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 8}})

    adapter = TelegramAdapter(
        token="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    assert await adapter.send_stored_file("555", "DOC-1") == "8"
    assert calls == ["sendPhoto", "sendDocument"]


async def test_the_call_table_covers_every_outgoing_method():
    """A method with no case here is a method nothing proves works."""
    import inspect

    public = {
        name
        for name, member in inspect.getmembers(TelegramAdapter, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }
    missing = public - set(CALLS)
    assert not missing, f"outgoing methods with no test: {sorted(missing)}"
