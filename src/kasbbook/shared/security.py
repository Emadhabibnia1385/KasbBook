"""Password hashing, token minting and one-time link codes.

Nothing here ever stores a raw secret. Passwords are Argon2id; link and refresh
tokens are stored as SHA-256 digests, so a database leak cannot be replayed
against the running system.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

# Link codes are read aloud and retyped, so they avoid characters people
# confuse: no 0/O, no 1/I/L.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (InvalidHashError, ValueError):
        return True


def new_token(length: int = 32) -> str:
    """A URL-safe secret, shown to the user exactly once."""
    return secrets.token_urlsafe(length)


def new_link_code(length: int = 8) -> str:
    """A short code a person can type into another app without mistyping it."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def token_digest(token: str) -> str:
    """What we persist. The raw token exists only in the user's hands."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, digest: str) -> bool:
    return hmac.compare_digest(token_digest(token), digest)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def expires_in(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)


def is_expired(moment: Optional[datetime]) -> bool:
    if moment is None:
        return False
    # Values read back from SQLite lose their tzinfo; treat those as UTC rather
    # than crashing on a naive/aware comparison.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment <= utcnow()
