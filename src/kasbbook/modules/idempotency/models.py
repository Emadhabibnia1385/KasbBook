"""What a request sent with an Idempotency-Key did, so a retry can be told again.

A mobile client on a bad network, a webhook consumer and a queue worker all
retry. A retried request that moves money must not move it twice, so the first
answer is stored under the key and every retry gets that answer back instead
of doing the work again.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.database import Base, Timestamped, UUIDPrimaryKey


class IdempotencyKey(UUIDPrimaryKey, Timestamped, Base):
    """One key, for one person, on one route, and the answer it got.

    The row is written in the same transaction as the work it guards. If the
    work commits, so does the row and its stored answer; if the work fails, both
    roll back and the key is free to be used again. `status_code` is empty only
    while that first request is still running.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        Index("ix_idempotency_keys_scope", "user_id", "key", "method", "path", unique=True),
        Index("ix_idempotency_keys_expires", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 of what was sent, so the same key with a different body is caught
    # rather than answered with someone else's result.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
