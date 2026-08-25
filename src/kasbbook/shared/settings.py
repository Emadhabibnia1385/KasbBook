"""Configuration, read once from the environment.

Every value has a safe default except the ones that cannot have one. A missing
bot token is a startup failure with a clear message, not a confusing 401 later.

One process runs one provider. Which one is a setting, and the token, username
and webhook secret are read from that provider's own variables — so a Bale bot
and a Telegram bot are two units with two environment files, never one process
juggling two identities.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..modules.identity.models import Provider


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value.strip() if value else default


# The variable prefix each provider reads. TELEGRAM_ keeps its historical
# names so an existing deployment's .env keeps working untouched.
PREFIXES = {
    Provider.TELEGRAM: "TELEGRAM",
    Provider.BALE: "BALE",
    Provider.RUBIKA: "RUBIKA",
    Provider.EITAA: "EITAA",
}

# Where BotFather's equivalent lives, so the error message is actionable
# instead of just correct.
WHERE_TO_GET_A_TOKEN = {
    Provider.TELEGRAM: "@BotFather on Telegram",
    Provider.BALE: "@BotFather on Bale",
    Provider.RUBIKA: "@BotFather on Rubika",
    Provider.EITAA: "the Eitaa bot panel",
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    provider: Provider = Provider.TELEGRAM
    telegram_token: Optional[str] = None
    telegram_bot_username: str = ""
    telegram_webhook_secret: Optional[str] = None
    bale_token: Optional[str] = None
    bale_bot_username: str = ""
    rubika_token: Optional[str] = None
    rubika_bot_username: str = ""
    redis_url: Optional[str] = None
    web_base_url: str = ""
    api_secret_key: Optional[str] = None
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    log_level: str = "INFO"

    @property
    def uses_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    # The three per-provider values, resolved for whichever one is running.
    @property
    def token(self) -> Optional[str]:
        return getattr(self, f"{self.provider.value}_token", None)

    @property
    def bot_username(self) -> str:
        return getattr(self, f"{self.provider.value}_bot_username", "") or ""

    @property
    def webhook_secret(self) -> Optional[str]:
        return getattr(self, f"{self.provider.value}_webhook_secret", None)

    @classmethod
    def from_env(cls) -> "Settings":
        # SQLite by default so a developer can run the bot without standing up
        # Postgres first. Production overrides this.
        database_url = _env("KASBBOOK_DATABASE_URL", "sqlite+aiosqlite:///kasbbook.db")

        raw_provider = (_env("KASBBOOK_PROVIDER", "telegram") or "telegram").lower()
        try:
            provider = Provider(raw_provider)
        except ValueError:
            raise RuntimeError(
                f"KASBBOOK_PROVIDER={raw_provider!r} is not a provider. "
                f"Choose one of: {', '.join(p.value for p in PREFIXES)}"
            ) from None

        return cls(
            database_url=database_url,
            provider=provider,
            telegram_token=_env("TELEGRAM_BOT_TOKEN"),
            telegram_bot_username=_env("TELEGRAM_BOT_USERNAME", "") or "",
            telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
            bale_token=_env("BALE_BOT_TOKEN"),
            bale_bot_username=_env("BALE_BOT_USERNAME", "") or "",
            rubika_token=_env("RUBIKA_BOT_TOKEN"),
            rubika_bot_username=_env("RUBIKA_BOT_USERNAME", "") or "",
            redis_url=_env("REDIS_URL"),
            web_base_url=_env("KASBBOOK_WEB_URL", "") or "",
            api_secret_key=_env("KASBBOOK_SECRET_KEY"),
            access_token_minutes=int(_env("KASBBOOK_ACCESS_MINUTES", "30") or 30),
            refresh_token_days=int(_env("KASBBOOK_REFRESH_DAYS", "30") or 30),
            log_level=_env("KASBBOOK_LOG_LEVEL", "INFO") or "INFO",
        )

    def require_token(self) -> str:
        """The running provider's token, or a startup failure that says what to do."""
        if not self.token:
            prefix = PREFIXES.get(self.provider, self.provider.value.upper())
            raise RuntimeError(
                f"{prefix}_BOT_TOKEN is not set. Create a bot with "
                f"{WHERE_TO_GET_A_TOKEN.get(self.provider, 'the provider')} and put "
                f"its token in the environment before starting the bot."
            )
        return self.token

    # Kept because it reads better at the Telegram-only call sites and because
    # an existing deployment may still call it.
    def require_telegram(self) -> str:
        if not self.telegram_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather and "
                "put its token in the environment before starting the bot."
            )
        return self.telegram_token

    def require_secret_key(self) -> str:
        """The API's signing key. There is no safe default for this one."""
        if not self.api_secret_key:
            raise RuntimeError(
                "KASBBOOK_SECRET_KEY is not set. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
                "and put it in the environment. Tokens signed with a guessable "
                "key are not tokens."
            )
        return self.api_secret_key
