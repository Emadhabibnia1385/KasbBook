"""Daily digest and loan installment reminders."""

from datetime import datetime, timedelta
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from typing import Dict, List, Optional

from .access import resolve_scope_owner
from .budgets import budget_status
from .config import CB_M, CB_RM, JOB_DIGEST, PRIMARY_ADMIN_USER_ID, TZ, logger
from .debts import debt_totals
from .jalali import g_to_j, g_to_j_parts
from .ledger import daily_list_text
from .loans import next_unpaid_due
from .money import fmt_money
from .store import db, get_setting
from .text import ikb, rtl
from .timeutil import today_g

def upcoming_loan_reminders(days_ahead: Optional[int] = None) -> List[Dict]:
    """Loans whose next installment falls within the warning window."""
    try:
        if get_setting("loan_reminder_enabled") != "1":
            return []
        window = days_ahead if days_ahead is not None else int(get_setting("loan_reminder_days"))
    except Exception:
        return []

    today = datetime.now(TZ).date()
    cutoff = (today + timedelta(days=max(0, window))).strftime("%Y-%m-%d")

    with db() as conn:
        loans = list(conn.execute("SELECT * FROM loans WHERE is_active=1").fetchall())

    out: List[Dict] = []
    for loan in loans:
        due = next_unpaid_due(str(loan["scope"]), int(loan["owner_user_id"]), loan)
        if due and due <= cutoff:
            out.append({
                "scope": str(loan["scope"]),
                "owner": int(loan["owner_user_id"]),
                "loan": loan,
                "due": due,
            })
    return out

def digest_text(scope: str, owner: int) -> str:
    parts = [daily_list_text(scope, owner, today_g())]

    totals = debt_totals(scope, owner)
    if totals["owed_to_me"] or totals["i_owe"]:
        parts.append(rtl(
            f"🤝 طلب: {fmt_money(totals['owed_to_me'])} | "
            f"بدهی: {fmt_money(totals['i_owe'])}"
        ))

    jy, jm, _ = g_to_j_parts(today_g())
    over = [b for b in budget_status(scope, owner, jy, jm) if b["spent"] > b["limit"]]
    if over:
        names = "، ".join(b["label"] for b in over[:3])
        parts.append(rtl(f"⛔ بودجهٔ رد شده: {names}"))

    return "\n\n".join(parts)

def reminders_kb() -> InlineKeyboardMarkup:
    digest_on = get_setting("digest_enabled") == "1"
    loan_on = get_setting("loan_reminder_enabled") == "1"
    hour = get_setting("digest_hour")
    days = get_setting("loan_reminder_days")

    return ikb([
        [(f"📊 خلاصهٔ روزانه: {'روشن ✅' if digest_on else 'خاموش ❌'}", f"{CB_RM}:tog:digest")],
        [(f"🕘 ساعت ارسال: {hour}", f"{CB_RM}:hour")],
        [(f"📄 یادآور قسط: {'روشن ✅' if loan_on else 'خاموش ❌'}", f"{CB_RM}:tog:loan")],
        [(f"⏳ چند روز قبل: {days}", f"{CB_RM}:days")],
        [("⬅️ بازگشت", f"{CB_M}:st")],
    ])

def reminders_text() -> str:
    return (
        "🔔 یادآورها\n\n"
        "خلاصهٔ روزانه هر شب وضعیت همان روز را می‌فرستد.\n"
        "یادآور قسط، قبل از سررسید هر قسط خبر می‌دهد."
    )

async def digest_job(ctx) -> None:
    """Runs hourly; sends what is due this hour and nothing twice."""
    try:
        now = datetime.now(TZ)
        stamp = now.strftime("%Y-%m-%d")
        app = ctx.application

        if get_setting("digest_enabled") == "1":
            try:
                hour = int(get_setting("digest_hour"))
            except (TypeError, ValueError):
                hour = 21

            if now.hour == hour and app.bot_data.get("digest_sent_on") != stamp:
                app.bot_data["digest_sent_on"] = stamp
                scope, owner = resolve_scope_owner(PRIMARY_ADMIN_USER_ID)
                try:
                    await ctx.bot.send_message(PRIMARY_ADMIN_USER_ID, digest_text(scope, owner))
                except Exception as e:
                    logger.warning("Digest send failed: %s", e)

        if app.bot_data.get("loan_reminded_on") != stamp:
            due = upcoming_loan_reminders()
            if due:
                app.bot_data["loan_reminded_on"] = stamp
                lines = ["🔔 یادآور قسط", ""]
                for item in due:
                    lines.append(
                        f"• {item['loan']['title']}: "
                        f"{fmt_money(int(item['loan']['installment_amount']))} "
                        f"— {g_to_j(item['due'])}"
                    )
                try:
                    await ctx.bot.send_message(PRIMARY_ADMIN_USER_ID, rtl("\n".join(lines)))
                except Exception as e:
                    logger.warning("Loan reminder send failed: %s", e)

    except Exception as e:
        logger.exception("Digest job failed: %s", e)

def schedule_digest_job(app: Application) -> None:
    try:
        for j in app.job_queue.get_jobs_by_name(JOB_DIGEST):
            j.schedule_removal()
    except Exception:
        pass

    app.job_queue.run_repeating(
        callback=digest_job, interval=3600, first=60, name=JOB_DIGEST
    )
