"""The contract every messenger speaks.

An adapter translates one provider's payloads into the models below and back.
That is *all* it does: no adapter reads or writes a financial table, and no
adapter decides what a user is allowed to do. Swapping Telegram for Bale changes
nothing above this line.

Providers differ in what they can do — Rubika has no message editing in the same
shape, Eitaa publishes no bot API at all — so each adapter declares its
`Capabilities` and the layer above degrades instead of failing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Sequence

from ..modules.identity.models import Provider


class EventKind(str, enum.Enum):
    COMMAND = "command"
    MESSAGE = "message"
    CALLBACK = "callback"
    ATTACHMENT = "attachment"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChannelIdentity:
    """Who sent this, in the provider's own terms.

    Resolving it to a KasbBook account is the identity module's job, never the
    adapter's.
    """

    provider: Provider
    external_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None


@dataclass(frozen=True)
class Attachment:
    kind: str                      # photo | document | voice | other
    file_id: str                   # opaque, provider-specific
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass(frozen=True)
class Button:
    text: str
    data: Optional[str] = None     # callback payload
    url: Optional[str] = None      # link instead of a callback

    def __post_init__(self) -> None:
        if not self.data and not self.url:
            raise ValueError("a button needs either callback data or a url")


@dataclass(frozen=True)
class IncomingEvent:
    """One thing a user did, in a shape that is the same on every provider."""

    kind: EventKind
    identity: ChannelIdentity
    chat_id: str
    message_id: Optional[str] = None
    text: Optional[str] = None
    command: Optional[str] = None
    args: Optional[str] = None
    callback_data: Optional[str] = None
    callback_id: Optional[str] = None
    attachment: Optional[Attachment] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutgoingFile:
    """Something the user keeps, rather than a screen they read."""

    content: bytes
    filename: str
    caption: Optional[str] = None


@dataclass(frozen=True)
class OutgoingMessage:
    """One screen to show. `edit_message_id` asks to replace rather than append."""

    chat_id: str
    text: str
    buttons: Sequence[Sequence[Button]] = ()
    edit_message_id: Optional[str] = None
    # A file is sent alongside the screen, never instead of it: an export is
    # something you scroll back to, so it must not be edited away later.
    document: Optional[OutgoingFile] = None
    # A file the provider is already storing, forwarded by its own id rather
    # than downloaded and re-uploaded. Receipts work this way. The kind travels
    # with it so the adapter can pick the right method instead of trying one
    # and wearing the rejection; None means it was attached before kinds were
    # recorded, and the adapter falls back to guessing.
    forward_file_id: Optional[str] = None
    forward_file_kind: Optional[str] = None
    # Something the reader should have to reveal deliberately — an API key on a
    # screen somebody may be showing to a colleague. Providers that cannot
    # conceal text still have to show it, so this degrades to a plain line
    # rather than being dropped: a key nobody can see is worse than one that is
    # merely not hidden.
    hidden: Optional[str] = None


@dataclass(frozen=True)
class Capabilities:
    """What this provider can actually do.

    Anything false here is switched off in the UI rather than attempted and
    failed. A missing capability never removes the feature from the web panel.
    """

    inline_buttons: bool = True
    edit_message: bool = True
    delete_message: bool = True
    send_file: bool = True
    receive_file: bool = True
    deep_link: bool = True
    webhook: bool = True
    polling: bool = True
    # Whether the provider can conceal a run of text behind a tap.
    spoiler: bool = False


class MessagingAdapter(Protocol):
    """What every provider adapter implements."""

    provider: Provider
    capabilities: Capabilities

    def verify_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """Reject anything not provably from this provider."""

    def parse_event(self, payload: Dict[str, Any]) -> Optional[IncomingEvent]:
        """Provider payload in, internal event out. None for updates we ignore."""

    def identify_user(self, event: IncomingEvent) -> ChannelIdentity:
        ...

    async def send_message(self, message: OutgoingMessage) -> Optional[str]:
        """Returns the new message id, when the provider gives one."""

    async def edit_message(self, message: OutgoingMessage) -> Optional[str]:
        ...

    async def send_file(
        self, chat_id: str, content: bytes, filename: str, caption: Optional[str] = None
    ) -> Optional[str]:
        ...

    async def answer_callback(self, callback_id: str, text: Optional[str] = None) -> None:
        ...

    def build_buttons(self, buttons: Sequence[Sequence[Button]]) -> Any:
        """Internal buttons rendered in the provider's own keyboard format."""

    def create_deep_link(self, payload: str) -> str:
        """A link that opens this bot and hands it `payload`."""
