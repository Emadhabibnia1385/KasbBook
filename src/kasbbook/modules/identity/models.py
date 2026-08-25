"""One account, many identities.

A person reaches KasbBook from Telegram, Bale, Rubika, Eitaa or the web. All of
those are *identities* pointing at a single `User`, which is what every book,
transaction and permission actually hangs off. No messenger id is ever the
account itself, because a person can lose or change any of them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    text,
    Integer,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...shared.database import Base, Timestamped, UUIDPrimaryKey


class Provider(str, enum.Enum):
    """Where an identity came from. `WEB` is the account's own login."""

    WEB = "web"
    TELEGRAM = "telegram"
    BALE = "bale"
    RUBIKA = "rubika"
    EITAA = "eitaa"


MESSENGERS = (Provider.TELEGRAM, Provider.BALE, Provider.RUBIKA, Provider.EITAA)


class LinkDirection(str, enum.Enum):
    """Which side started the link, which decides what the token is bound to."""

    FROM_WEB = "from_web"          # bound to a user, waiting for a messenger
    FROM_MESSENGER = "from_messenger"  # bound to a messenger identity, waiting for a login


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="fa")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Tehran")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Notification preferences. On by default: a bookkeeping tool that never
    # speaks first is one people forget to open. The hour is local to the
    # user's own timezone, not the server's.
    digest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    digest_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=21, server_default=text("21")
    )
    reminder_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )

    identities: Mapped[list["Identity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.display_name!r}>"


class Identity(UUIDPrimaryKey, Timestamped, Base):
    """A messenger account attached to a `User`.

    The unique constraint on (provider, external_id) is the rule that one
    Telegram account cannot end up feeding two different sets of books.
    """

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="one_account_per_external_identity"),
        Index("ix_identities_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider, native_enum=False, length=16), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_username: Mapped[Optional[str]] = mapped_column(String(120))
    display_name: Mapped[Optional[str]] = mapped_column(String(120))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="identities", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Identity {self.provider.value}:{self.external_id} -> {self.user_id}>"


class LinkToken(UUIDPrimaryKey, Timestamped, Base):
    """A one-time, expiring proof used to attach an identity to an account.

    Only the digest is stored. Whichever side started the flow fills in its half
    (`user_id` from the web, `provider`+`external_id` from a messenger) and the
    other half arrives when the token is redeemed.
    """

    __tablename__ = "link_tokens"
    __table_args__ = (
        Index("ix_link_tokens_digest", "token_digest", unique=True),
        Index("ix_link_tokens_user", "user_id"),
    )

    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[LinkDirection] = mapped_column(
        Enum(LinkDirection, native_enum=False, length=20), nullable=False
    )

    # Filled by the side that started the flow.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    provider: Mapped[Optional[Provider]] = mapped_column(
        Enum(Provider, native_enum=False, length=16)
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(64))
    external_username: Mapped[Optional[str]] = mapped_column(String(120))

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def is_open(self) -> bool:
        return self.consumed_at is None and self.revoked_at is None


class AuditEvent(UUIDPrimaryKey, Timestamped, Base):
    """Append-only record of anything that changes who can see what."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_user_action", "user_id", "action"),)

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(120))
    detail: Mapped[Optional[str]] = mapped_column(Text)
