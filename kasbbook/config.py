"""Environment, constants and logging setup."""

import asyncio
import logging
import os
import pytz
from dotenv import load_dotenv

# =========================
# Config / Constants
# =========================
PROJECT_NAME = "KasbBook"

DB_PATH = "KasbBook.db"

BACKUP_DIR = "backups"       # on-disk safety copies, used to undo a failed restore

TZ = pytz.timezone("Asia/Tehran")

# Telegram refuses very large inline keyboards, so every long list is paged.
DAILY_PAGE_SIZE = 8          # transaction rows per section in the daily list

CAT_PAGE_SIZE = 24           # categories per page

ADMIN_PAGE_SIZE = 20         # admins per page

TOP_CATEGORIES = 8           # rows per group in the category breakdown report

SEARCH_PAGE_SIZE = 10        # search results per page

LOAN_PAGE_SIZE = 10          # loans per page

BUDGET_PAGE_SIZE = 10        # budgets per page

DEBT_PAGE_SIZE = 10          # debts per page

DEFAULT_CURRENCY = "تومان"

# Guard rails for public mode, where anyone can start the bot.
PUBLIC_MAX_TX_PER_DAY = 300

PUBLIC_MAX_CATEGORIES = 200

ACCESS_ADMIN_ONLY = "admin_only"   # default

ACCESS_PUBLIC = "public"

INSTALLMENT_NAME = "قسط"

RLM = "\u200f"       # RTL mark

ZWSP = "\u200b"      # non-empty invisible char

# Callback prefixes (short)
CB_M = "m"      # main

CB_ST = "st"    # settings

CB_AC = "ac"    # access

CB_AD = "ad"    # admin manage

CB_CT = "ct"    # categories

CB_TX = "tx"    # transaction flow + menus

CB_DL = "dl"    # daily list

CB_DTX = "dtx"  # tx detail/edit

CB_RP = "rp"    # reports

CB_DB = "db"    # database/backup

CB_LN = "ln"    # loans / installments

CB_RC = "rc"    # recurring transactions

CB_SR = "sr"    # search

CB_CU = "cu"    # currency

CB_BG = "bg"    # budgets

CB_DT = "dt"    # debts and receivables

CB_TR = "tr"    # trend chart

CB_RM = "rm"    # reminders and digest

# Job name
JOB_BACKUP = "kasbbook_auto_backup"

JOB_RECURRING = "kasbbook_recurring"

JOB_DIGEST = "kasbbook_digest"

# Global DB lock to reduce "database is locked"
DB_LOCK = asyncio.Lock()

# =========================
# ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID")       # backward compatible (old name)

ADMIN_USERNAME_RAW = os.getenv("ADMIN_USERNAME")

# Optional new env (recommended)
PRIMARY_ADMIN_USER_ID_RAW = os.getenv("PRIMARY_ADMIN_USER_ID")

if not BOT_TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is not set")

if not ADMIN_CHAT_ID_RAW:
    raise RuntimeError("ENV ADMIN_CHAT_ID is not set")

if not ADMIN_USERNAME_RAW:
    raise RuntimeError("ENV ADMIN_USERNAME is not set")

try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
except ValueError:
    raise RuntimeError("ENV ADMIN_CHAT_ID must be an integer")

# Primary admin user_id (new env if provided; else fallback to ADMIN_CHAT_ID)
if PRIMARY_ADMIN_USER_ID_RAW:
    try:
        PRIMARY_ADMIN_USER_ID = int(PRIMARY_ADMIN_USER_ID_RAW)
    except ValueError:
        raise RuntimeError("ENV PRIMARY_ADMIN_USER_ID must be an integer")
else:
    PRIMARY_ADMIN_USER_ID = ADMIN_CHAT_ID  # backward compatible

ADMIN_USERNAME = (ADMIN_USERNAME_RAW or "").strip()

if ADMIN_USERNAME.startswith("@"):
    ADMIN_USERNAME = ADMIN_USERNAME[1:]

if not ADMIN_USERNAME:
    raise RuntimeError("ENV ADMIN_USERNAME is invalid/empty")

# =========================
# Logging
# =========================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(PROJECT_NAME)

# httpx logs the full request URL at INFO, and for Telegram that URL contains
# the bot token — which would put the token in plaintext in journalctl on every
# single API call. These libraries stay at WARNING so nothing leaks into logs.
for _noisy in ("httpx", "httpcore", "telegram.vendor", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
