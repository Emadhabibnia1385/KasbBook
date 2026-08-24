"""Configuration, read once from the environment.

Every value has a safe default except the ones that cannot have one. A missing
bot token is a startup failure with a clear message, not a confusing 401 later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value.strip() if value else default


@dataclass(frozen=True)
class Settings:
    database_url: str
    telegram_token: Optional[str] = None
    telegram_bot_username: str = ""
    telegram_webhook_secret: Optional[str] = None
    redis_url: Optional[str] = None
    web_base_url: str = ""
    log_level: str = "INFO"

    @property
    def uses_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @classmethod
    def from_env(cls) -> "Settings":
        # SQLite by default so a developer can run the bot without standing up
        # Postgres first. Production overrides this.
        database_url = _env("KASBBOOK_DATABASE_URL", "sqlite+aiosqlite:///kasbbook.db")

        return cls(
            database_url=database_url,
            telegram_token=_env("TELEGRAM_BOT_TOKEN"),
            telegram_bot_username=_env("TELEGRAM_BOT_USERNAME", "") or "",
            telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
            redis_url=_env("REDIS_URL"),
            web_base_url=_env("KASBBOOK_WEB_URL", "") or "",
            log_level=_env("KASBBOOK_LOG_LEVEL", "INFO") or "INFO",
        )

    def require_telegram(self) -> str:
        if not self.telegram_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather and "
                "put its token in the environment before starting the bot."
            )
        return self.telegram_token
