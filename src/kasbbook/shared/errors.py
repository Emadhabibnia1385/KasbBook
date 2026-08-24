"""Domain errors.

These are raised by application services and translated once, at the edge, into
an HTTP status or a messenger reply. Nothing below the API layer knows what a
status code is.
"""

from __future__ import annotations


class KasbBookError(Exception):
    """Base for every error this system raises on purpose."""

    status_code = 400


class NotFound(KasbBookError):
    status_code = 404


class PermissionDenied(KasbBookError):
    status_code = 403


class InvalidLinkToken(KasbBookError):
    """A link code that is unknown, spent, expired or meant for another provider."""

    status_code = 400


class AlreadyLinked(KasbBookError):
    """The identity is already attached to the account doing the asking."""

    status_code = 409


class IdentityTakenError(KasbBookError):
    """The identity belongs to a different account and will not be moved silently."""

    status_code = 409


class ValidationError(KasbBookError):
    status_code = 422


class BalanceError(KasbBookError):
    """A journal entry whose debits and credits do not agree."""

    status_code = 422
