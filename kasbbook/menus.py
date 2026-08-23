"""Top-level navigation keyboards."""

from telegram import InlineKeyboardMarkup

from .access import is_primary_admin
from .config import ACCESS_ADMIN_ONLY, ACCESS_PUBLIC, CB_AC, CB_AD, CB_BG, CB_CT, CB_DL, CB_DT, CB_LN, CB_M, CB_RC, CB_RM, CB_ST, CB_TX
from .jalali import g_to_j
from .store import get_setting
from .text import ikb
from .timeutil import today_g
from .screen import single_message_on

# متن استارت (طبق درخواست شما تغییر نکند)
def start_text() -> str:
    return (
        "📊 KasbBook | مدیریت مالی کسب‌وکار\n\n"
        "با KasbBook می‌تونی:\n"
        "• درآمدها و هزینه‌ها رو ثبت کنی\n"
        "• گزارش روزانه، ماهانه و سالانه ببینی\n"
        "• پس‌انداز و سود واقعی کارت رو تحلیل کنی\n\n"
        "برای شروع از منوی زیر استفاده کن 👇\n\n"
        "🚀 شروع ربات با دستور: /start\n"
        "👨‍💻 Developer: @emadhabibnia"
    )

def main_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📌 تراکنش‌ها", f"{CB_M}:tx")],
            [("📊 گزارش", f"{CB_M}:report")],
            [("⚙️ تنظیمات", f"{CB_M}:st")],
        ]
    )

def tx_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("➕ اضافه کردن تراکنش جدید", f"{CB_TX}:new")],
            [("📄 لیست روزانه", f"{CB_DL}:pick")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )

def settings_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [("🧩 مدیریت دسته‌ها", f"{CB_ST}:cats")],
        [("📄 اقساط و وام‌ها", f"{CB_LN}:panel")],
        [("🤝 طلب و بدهی", f"{CB_DT}:panel")],
        [("🎯 بودجه‌ها", f"{CB_BG}:panel")],
        [("🔁 تراکنش‌های تکرارشونده", f"{CB_RC}:panel")],
        [("🔔 یادآورها", f"{CB_RM}:panel")],
        [("💱 واحد پول", f"{CB_ST}:cur")],
        [(f"🧹 حالت تک‌پیامی: {'روشن ✅' if single_message_on() else 'خاموش ❌'}", f"{CB_ST}:single")],
    ]
    if is_primary_admin(user_id):
        rows.append([("🔐 دسترسی ربات", f"{CB_ST}:access")])
        rows.append([("🗄 دیتابیس", f"{CB_ST}:db")])
    rows.append([("⬅️ بازگشت", f"{CB_M}:home")])
    return ikb(rows)

def access_menu(user_id: int) -> InlineKeyboardMarkup:
    mode = get_setting("access_mode")
    a = "✅" if mode == ACCESS_ADMIN_ONLY else ""
    p = "✅" if mode == ACCESS_PUBLIC else ""

    rows = [
        [(f"👑 حالت ادمین {a}", f"{CB_AC}:mode:{ACCESS_ADMIN_ONLY}")],
        [(f"🌐 حالت همگانی {p}", f"{CB_AC}:mode:{ACCESS_PUBLIC}")],
    ]

    if mode == ACCESS_ADMIN_ONLY and is_primary_admin(user_id):
        sh = get_setting("share_enabled")
        sh_txt = "روشن ✅" if sh == "1" else "خاموش ❌"
        rows.append([(f"🔁 اشتراک اطلاعات: {sh_txt}", f"{CB_AC}:share")])
        rows.append([("👥 مدیریت ادمین‌ها", f"{CB_AD}:panel")])

    rows.append([("⬅️ بازگشت", f"{CB_M}:home")])
    return ikb(rows)

def cats_root_menu() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_CT}:grp:work_in")],
            [("🏢 هزینه کاری", f"{CB_CT}:grp:work_out")],
            [("💵 درآمد شخصی", f"{CB_CT}:grp:personal_in")],
            [("👤 هزینه شخصی", f"{CB_CT}:grp:personal_out")],
            [("⬅️ بازگشت", f"{CB_M}:home")],
        ]
    )

def tx_date_menu_kb(back_cb: str) -> InlineKeyboardMarkup:
    g = today_g()
    j = g_to_j(g)
    return ikb(
        [
            [(f"✅ امروز ({g} / {j})", f"{CB_TX}:date:today")],
            [("🗓 تاریخ میلادی", f"{CB_TX}:date:g")],
            [("🧿 تاریخ شمسی", f"{CB_TX}:date:j")],
            [("⬅️ بازگشت", back_cb)],
        ]
    )

def tx_ttype_kb(back_cb: str) -> InlineKeyboardMarkup:
    return ikb(
        [
            [("💰 درآمد کاری", f"{CB_TX}:tt:work_in")],
            [("🏢 هزینه کاری", f"{CB_TX}:tt:work_out")],
            [("💵 درآمد شخصی", f"{CB_TX}:tt:personal_in")],
            [("👤 هزینه شخصی", f"{CB_TX}:tt:personal_out")],
            [("⬅️ بازگشت", back_cb)],
        ]
    )

# =========================
# Daily list
# =========================
def daily_pick_menu() -> InlineKeyboardMarkup:
    g = today_g()
    j = g_to_j(g)
    return ikb(
        [
            [(f"✅ امروز ({g} / {j})", f"{CB_DL}:d:today")],
            [("🗓 وارد کردن تاریخ میلادی", f"{CB_DL}:d:g")],
            [("🧿 وارد کردن تاریخ شمسی", f"{CB_DL}:d:j")],
            [("⬅️ بازگشت", f"{CB_M}:tx")],
        ]
    )
