"""Bale and Rubika, and the contract all three providers have to keep.

The valuable half of this file is the conformance suite at the bottom: the same
assertions, run against every adapter. A provider that quietly stops parsing a
button press or stops returning a message id fails there, not in production
three weeks later.

No network and no tokens — every call goes to a mock transport, so this runs
identically on a laptop and in CI.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

from kasbbook.adapters.bale import BaleAdapter
from kasbbook.adapters.base import Button, Capabilities, EventKind, OutgoingMessage
from kasbbook.adapters.rubika import RubikaAdapter
from kasbbook.adapters.telegram import TelegramAdapter
from kasbbook.modules.identity.models import Provider

pytestmark = pytest.mark.asyncio


class FakeBotApi:
    """Answers the way Telegram and Bale do: {"ok": true, "result": {...}}."""

    def __init__(self, ok: bool = True, message_id: int = 42) -> None:
        self.ok, self.message_id = ok, message_id
        self.calls: List[Dict[str, Any]] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content) if request.content else {}
        except (ValueError, UnicodeDecodeError):
            body = {"_multipart": True}
        self.calls.append({"url": str(request.url), "body": body,
                           "method": str(request.url).rsplit("/", 1)[-1]})
        if not self.ok:
            return httpx.Response(200, json={"ok": False, "description": "nope"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": self.message_id}})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))


class FakeRubika:
    """Answers the way Rubika does: {"status": "OK", "data": {...}}."""

    def __init__(self, ok: bool = True, message_id: str = "77") -> None:
        self.ok, self.message_id = ok, message_id
        self.calls: List[Dict[str, Any]] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content) if request.content else {}
        except (ValueError, UnicodeDecodeError):
            body = {"_multipart": True}
        method = str(request.url).rsplit("/", 1)[-1]
        self.calls.append({"url": str(request.url), "body": body, "method": method})

        if not self.ok:
            return httpx.Response(200, json={"status": "INVALID_INPUT"})
        if method == "requestSendFile":
            return httpx.Response(200, json={
                "status": "OK", "data": {"upload_url": "https://upload.rubika.test/x"}})
        if "upload.rubika.test" in str(request.url):
            return httpx.Response(200, json={"status": "OK", "data": {"file_id": "F1"}})
        return httpx.Response(200, json={
            "status": "OK", "data": {"message_id": self.message_id}})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))


def bale(fake=None) -> BaleAdapter:
    return BaleAdapter(token="T", bot_username="KasbBookBot",
                       client=(fake or FakeBotApi()).client())


def rubika(fake=None) -> RubikaAdapter:
    return RubikaAdapter(token="T", bot_username="KasbBookBot",
                         client=(fake or FakeRubika()).client())


# ==================================================================== Bale
async def test_bale_talks_to_bale_and_not_to_telegram():
    """The one mistake that would send every Iranian user's data abroad."""
    fake = FakeBotApi()
    await BaleAdapter(token="SECRET", client=fake.client()).send_plain("1", "سلام")

    assert fake.calls[0]["url"].startswith("https://tapi.bale.ai/botSECRET/")
    assert "api.telegram.org" not in fake.calls[0]["url"]


async def test_bale_parses_a_telegram_shaped_message_as_its_own_provider():
    event = bale().parse_event({
        "update_id": 1,
        "message": {"message_id": 5, "chat": {"id": 900},
                    "from": {"id": 900, "first_name": "عماد"}, "text": "سلام"},
    })

    assert event.kind is EventKind.MESSAGE
    assert event.text == "سلام"
    # Inherited parsing, but the identity must carry Bale — not Telegram.
    assert event.identity.provider is Provider.BALE
    assert event.identity.external_id == "900"


async def test_a_bale_button_press_is_a_callback():
    event = bale().parse_event({
        "update_id": 2,
        "callback_query": {"id": "cb9", "from": {"id": 900, "first_name": "عماد"},
                           "data": "book:list",
                           "message": {"message_id": 5, "chat": {"id": 900}}},
    })

    assert event.kind is EventKind.CALLBACK
    assert event.callback_data == "book:list"
    assert event.identity.provider is Provider.BALE


async def test_a_bale_deep_link_points_at_ble_ir():
    assert bale().create_deep_link("ABC") == "https://ble.ir/KasbBookBot?start=ABC"


async def test_bale_edits_the_screen_rather_than_appending():
    fake = FakeBotApi()
    await bale(fake).edit_message(OutgoingMessage("1", "تازه", edit_message_id="5"))

    assert fake.calls[0]["method"] == "editMessageText"
    assert fake.calls[0]["body"]["message_id"] == 5


async def test_bale_falls_back_to_a_new_message_when_the_edit_is_refused():
    fake = FakeBotApi(ok=False)
    await bale(fake).edit_message(OutgoingMessage("1", "تازه", edit_message_id="5"))

    assert [c["method"] for c in fake.calls] == ["editMessageText", "sendMessage"]


# ================================================================== Rubika
async def test_rubika_talks_to_the_official_bot_api():
    fake = FakeRubika()
    await RubikaAdapter(token="SECRET", client=fake.client()).send_plain("1", "سلام")

    assert fake.calls[0]["url"] == "https://botapi.rubika.ir/v3/SECRET/sendMessage"


async def test_rubika_reads_its_own_envelope():
    """`status: OK` and `data`, not `ok` and `result`."""
    assert await rubika().send_plain("900", "سلام") == "77"


async def test_a_rubika_refusal_is_not_mistaken_for_success():
    assert await rubika(FakeRubika(ok=False)).send_plain("900", "سلام") is None


async def test_a_rubika_button_press_arrives_as_a_message_and_becomes_a_callback():
    """The difference that would otherwise break every screen on Rubika."""
    event = rubika().parse_event({
        "type": "NewMessage", "chat_id": "b0ABC",
        "new_message": {"message_id": "112", "text": "دفترها", "sender_type": "User",
                        "sender_id": "u77", "aux_data": {"button_id": "book:list"}},
    })

    assert event.kind is EventKind.CALLBACK
    assert event.callback_data == "book:list"
    assert event.chat_id == "b0ABC"
    assert event.identity.external_id == "u77"
    # Nothing is spinning, so there is no callback id to answer.
    assert event.callback_id is None


async def test_a_plain_rubika_message_stays_a_message():
    event = rubika().parse_event({
        "chat_id": "b0ABC",
        "new_message": {"message_id": "113", "text": "۲۵۰ک", "sender_id": "u77"},
    })

    assert event.kind is EventKind.MESSAGE
    assert event.text == "۲۵۰ک"


async def test_a_rubika_deep_link_payload_arrives_beside_the_text():
    """Rubika puts the /start argument in aux_data, not in the message text."""
    event = rubika().parse_event({
        "chat_id": "b0ABC",
        "new_message": {"message_id": "1", "text": "/start", "sender_id": "u77",
                        "aux_data": {"start_id": "LINKTOKEN"}},
    })

    assert event.kind is EventKind.COMMAND
    assert event.command == "start"
    assert event.args == "LINKTOKEN"


async def test_a_rubika_slash_command_without_aux_data_still_parses():
    event = rubika().parse_event({
        "chat_id": "b0ABC",
        "new_message": {"message_id": "1", "text": "/help", "sender_id": "u77"},
    })

    assert event.kind is EventKind.COMMAND
    assert event.command == "help"


async def test_rubika_buttons_carry_the_payload_in_the_id():
    """Rubika hands back `id` on a press, so that is where the payload has to live."""
    keypad = rubika().build_buttons([[Button("دفترها", data="book:list")]])
    button = keypad["rows"][0]["buttons"][0]

    assert button["id"] == "book:list"
    assert button["button_text"] == "دفترها"
    assert button["type"] == "Simple"


async def test_a_rubika_url_button_is_a_link_not_a_callback():
    keypad = rubika().build_buttons([[Button("راهنما", url="https://kasbbook.ir")]])
    button = keypad["rows"][0]["buttons"][0]

    assert button["type"] == "Link"
    assert button["button_link"]["link_url"] == "https://kasbbook.ir"


async def test_editing_on_rubika_replaces_the_keyboard_too():
    """Editing text leaves the old buttons in place, which strands the screen."""
    fake = FakeRubika()
    await rubika(fake).edit_message(
        OutgoingMessage("b0", "تازه", [[Button("خانه", data="nav:home")]],
                        edit_message_id="112")
    )

    assert [c["method"] for c in fake.calls] == ["editMessageText", "editMessageKeypad"]


async def test_a_rubika_upload_asks_for_a_url_first():
    """Rubika does not accept bytes on the API host; it hands out an upload URL."""
    fake = FakeRubika()
    assert await rubika(fake).send_file("b0", b"a,b\n1,2\n", "export.csv") == "77"

    assert [c["method"] for c in fake.calls][0] == "requestSendFile"
    assert [c["method"] for c in fake.calls][-1] == "sendFile"


async def test_a_rubika_upload_that_never_gets_a_url_gives_up_cleanly():
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "OK", "data": {}})

    adapter = RubikaAdapter(
        token="T", client=httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )
    assert await adapter.send_file("b0", b"x", "f.csv") is None


async def test_rubika_pages_with_its_own_cursor():
    """An opaque `next_offset_id`, carried into the next call."""
    pages = [
        {"status": "OK", "data": {"updates": [{"chat_id": "1"}], "next_offset_id": "N2"}},
        {"status": "OK", "data": {"updates": [], "next_offset_id": "N3"}},
    ]
    seen: List[Dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=pages[len(seen) - 1])

    adapter = RubikaAdapter(
        token="T", client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    first = await adapter.fetch_updates()
    assert first.ok and len(first.updates) == 1
    assert "offset_id" not in seen[0]

    await adapter.fetch_updates()
    assert seen[1]["offset_id"] == "N2"


async def test_answering_a_rubika_callback_does_nothing_and_says_so():
    fake = FakeRubika()
    await rubika(fake).answer_callback("whatever")
    assert fake.calls == []


# ============================================== the contract, on every one
#
# Everything below runs identically against all three adapters. A provider that
# stops honouring one of these has broken the promise the conversation layer is
# written against.

ADAPTERS = {
    "telegram": (lambda: TelegramAdapter(token="T", bot_username="B",
                                         client=FakeBotApi().client()), FakeBotApi),
    "bale": (lambda: BaleAdapter(token="T", bot_username="B",
                                 client=FakeBotApi().client()), FakeBotApi),
    "rubika": (lambda: RubikaAdapter(token="T", bot_username="B",
                                     client=FakeRubika().client()), FakeRubika),
}


def _build(name):
    """A fresh adapter and the fake it is wired to, so calls can be inspected."""
    factory, fake_class = ADAPTERS[name]
    fake = fake_class()
    adapter = factory()
    adapter._client = fake.client()
    return adapter, fake


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_declares_a_provider_and_capabilities(name):
    adapter, _ = _build(name)
    assert isinstance(adapter.provider, Provider)
    assert isinstance(adapter.capabilities, Capabilities)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_returns_a_message_id_it_can_edit_later(name):
    """The single-screen UX depends on this; without an id it appends forever."""
    adapter, _ = _build(name)
    message_id = await adapter.send_message(
        OutgoingMessage("1", "سلام", [[Button("خانه", data="nav:home")]])
    )
    assert message_id, f"{name} returned no message id"


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_sends_the_buttons_it_was_given(name):
    adapter, fake = _build(name)
    await adapter.send_message(
        OutgoingMessage("1", "سلام", [[Button("دفترها", data="book:list")]])
    )
    assert "book:list" in json.dumps(fake.calls[0]["body"], ensure_ascii=False)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_ignores_an_update_it_has_no_business_with(name):
    adapter, _ = _build(name)
    assert adapter.parse_event({"update_id": 1, "poll": {"id": "p"}}) is None


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_refuses_a_deep_link_without_a_username(name):
    factory, fake_class = ADAPTERS[name]
    adapter = factory()
    adapter.bot_username = ""
    with pytest.raises(ValueError):
        adapter.create_deep_link("ABC")


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_reports_an_unreachable_provider_as_unreachable(name):
    """Not as "no updates" — that is how a bot spins silently against a dead token."""
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    factory, _ = ADAPTERS[name]
    adapter = factory()
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(explode))

    batch = await adapter.fetch_updates()
    assert batch.unreachable and not batch.ok


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_reports_a_refusal_as_a_refusal(name):
    adapter, _ = _build(name)
    factory, fake_class = ADAPTERS[name]
    adapter._client = fake_class(ok=False).client()

    batch = await adapter.fetch_updates()
    assert batch.refused and not batch.ok and not batch.unreachable


@pytest.mark.parametrize("name", sorted(ADAPTERS))
async def test_every_adapter_implements_the_whole_protocol(name):
    """A missing method is a crash the first time that screen is opened."""
    adapter, _ = _build(name)
    required = (
        "verify_webhook", "parse_event", "identify_user", "build_buttons",
        "create_deep_link", "send_message", "edit_message", "delete_message",
        "send_file", "send_stored_file", "send_plain", "answer_callback",
        "set_webhook", "delete_webhook", "get_me", "fetch_updates", "aclose",
    )
    missing = [name for name in required if not hasattr(adapter, name)]
    assert not missing, missing
