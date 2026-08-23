"""Current-time helpers, all in the bot's timezone."""

from datetime import datetime

from .config import TZ

def now_ts() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def today_g() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")
