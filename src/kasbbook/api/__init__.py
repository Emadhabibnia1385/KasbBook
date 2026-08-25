"""The HTTP API.

Everything here is a thin edge: it parses a request, calls an application
service, and translates the result. No business rule lives in this package —
if a rule were here, the bot would not obey it, and the bot is where most
people actually use this.
"""

from __future__ import annotations
