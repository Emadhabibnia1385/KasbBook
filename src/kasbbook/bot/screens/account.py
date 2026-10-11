"""The account screens: profile, password, messengers, API key, sessions."""

from __future__ import annotations

from typing import Iterable, List

from ...adapters.base import Button
from ...modules.identity.models import Identity, Provider
from ...shared import jalali
from .common import (
    Screen,
    rtl,
)


PROVIDER_LABELS = {
    Provider.TELEGRAM: "تلگرام",
    Provider.BALE: "بله",
    Provider.RUBIKA: "روبیکا",
    Provider.EITAA: "ایتا",
    Provider.WEB: "وب",
}


def not_linked(code: str) -> Screen:
    """Shown when this messenger account is not attached to any KasbBook account."""
    text = rtl(
        "این حساب هنوز به KasbBook وصل نیست.\n\n"
        "دو راه داری:\n\n"
        "1. اگر حساب داری، در پنل وب وارد شو و این کد را وارد کن:\n"
        f"    {code}\n\n"
        "2. اگر نداری، همین‌جا یک حساب تازه بساز.\n\n"
        "کد تا 15 دقیقه معتبر است."
    )
    return text, [
        [Button("🆕 ساخت حساب تازه", data="acc:create")],
        [Button("🔄 کد جدید", data="acc:newcode")],
    ]


# -------------------------------------------------------- linked identities
def account_created(display_name: str) -> Screen:
    """A brand-new account is reachable from this messenger and nowhere else.

    Saying so now is much cheaper than explaining it to someone who has lost
    their Telegram account and their books with it.
    """
    return rtl(
        f"✅ حسابت ساخته شد، {display_name}.\n\n"
        "فعلاً فقط از همین پیام‌رسان به آن می‌رسی. اگر این حساب را از دست بدهی، "
        "دفترهایت هم می‌روند.\n\n"
        "یک ایمیل یا شماره اضافه کن تا حسابت راه برگشت داشته باشد."
    ), [
        [Button("📧 افزودن ایمیل یا شماره", data="acc:contact")],
        [Button("بعداً", data="nav:home")],
    ]


def account_panel(user, identities: Iterable[Identity], current: Provider) -> Screen:
    """Everything about the account itself, rather than about its books."""
    rows = list(identities)
    lines = [f"👤 {user.display_name}", ""]

    lines.append(f"📧 ایمیل: {user.email or 'ندارد'}")
    lines.append(f"📱 شماره: {user.phone or 'ندارد'}")
    lines.append(f"🔑 رمز: {'دارد' if user.password_hash else 'ندارد'}")
    lines.append(f"🕐 منطقهٔ زمانی: {user.timezone}")

    lines += ["", "🔗 پیام‌رسان‌های متصل:"]
    for identity in rows:
        label = PROVIDER_LABELS.get(identity.provider, identity.provider.value)
        who = identity.external_username or identity.external_id
        here = " ← همین‌جا" if identity.provider is current else ""
        lines.append(f"  • {label}: {who}{here}")

    if not user.email and not user.phone:
        lines += [
            "",
            "⚠️ این حساب راه برگشت ندارد. اگر پیام‌رسانت را از دست بدهی، "
            "دفترهایت هم می‌روند.",
        ]
    elif not user.password_hash:
        lines += ["", "برای ورود از وب یا API، یک رمز تعیین کن."]

    return rtl("\n".join(lines)), [
        [Button("✏️ نام", data="acc:name"),
         Button("🕐 منطقهٔ زمانی", data="acc:tz")],
        [Button("📧 ایمیل", data="acc:email"),
         Button("📱 شماره", data="acc:phone")],
        [Button("🔑 " + ("تغییر رمز" if user.password_hash else "تعیین رمز"),
                data="acc:pw")],
        [Button("🖥 نشست‌های فعال", data="acc:sessions"),
         Button("🔌 API", data="acc:api")],
        [Button("🗑 حذف حساب", data="acc:close")],
        [Button("🔐 ورود به حساب دیگر", data="acc:login")],
        [Button("👥 دعوت‌های تیمی", data="iv:inbox")],
        [Button("⬅️ بازگشت", data="nav:home")],
    ]


def _reading(docs_url: str, guide_url: str) -> List[List[Button]]:
    """The two places to read, side by side, and neither if there is nowhere.

    They answer different questions. The reference lists the endpoints and is
    what somebody writing a script needs open; the guide is what explains why
    money crosses as a string and why a period is Jalali — the things that turn
    a working request into a correct one. Linking only the reference left the
    second question with no answer reachable from inside the bot.

    An unset URL produces no button rather than a dead one.
    """
    row = []
    if docs_url:
        row.append(Button("📄 مرجع API", url=f"{docs_url.rstrip('/')}/docs"))
    if guide_url:
        row.append(Button("📗 راهنما", url=guide_url))
    return [row] if row else []


def api_panel(keys, docs_url: str = "", guide_url: str = "") -> Screen:
    """Where a person gets a credential for something that is not a person.

    An API key is issued once and stored as a digest, so this screen can never
    show an existing one — only its first few characters, which is enough to
    recognise it in a list. That is the whole reason a leaked database is worth
    nothing, and it is worth saying on the screen rather than leaving somebody
    hunting for a key that cannot be displayed.
    """
    rows = list(keys)
    lines = ["🔌 دسترسی API", ""]

    if not rows:
        lines.append(
            "با یک کلید API می‌توانی از بیرون — اسکریپت، صفحهٔ گسترده، هر برنامه‌ای — "
            "درآمد و هزینه ثبت کنی و گزارش بگیری.\n\n"
            "کلید هنوز نساخته‌ای."
        )
    else:
        lines.append("کلیدهای فعال:")
        for key in rows:
            used = "استفاده‌شده" if key.last_used_at else "هنوز استفاده نشده"
            lines.append(f"  • {key.prefix}…  ({used})")
        lines += [
            "",
            "کلید فقط یک بار، همان لحظهٔ ساخت، نشان داده می‌شود و بعد از آن فقط "
            "همین چند نویسهٔ اول باقی می‌ماند — چون خودش ذخیره نمی‌شود، فقط اثر "
            "انگشتش. اگر گمش کردی، کلید تازه بساز؛ برگرداندن قدیمی ممکن نیست.",
        ]

    buttons: List[List[Button]] = _reading(docs_url, guide_url)
    buttons.append([
        Button("🔄 کلید تازه" if rows else "🔑 ساخت کلید", data="acc:apinew")
    ])
    buttons.append([Button("⬅️ بازگشت", data="acc:panel")])
    return rtl("\n".join(lines)), buttons


def api_key_created(
    key: str, replaced: bool, docs_url: str = "", guide_url: str = ""
) -> Screen:
    """The only screen that ever contains the key itself.

    The key goes in `hidden`, not in the body, so a provider that can conceal
    text does — somebody may be reading this over a shoulder or sharing a
    screen. Providers that cannot still show it, because a key nobody can see
    is worse than one that is merely not hidden.
    """
    lines = ["🔑 کلید API"]
    if replaced:
        lines.append("کلید قبلی از همین حالا کار نمی‌کند.")
    lines += [
        "",
        "این تنها باری است که کامل نشانش می‌دهیم. جای امنی نگهش دار.",
        "",
        "برای استفاده، در هر درخواست این هدر را بفرست:",
        "X-API-Key: <کلید>",
        "",
        "👇 برای دیدن، روی خط زیر بزن",
    ]

    buttons: List[List[Button]] = _reading(docs_url, guide_url)
    buttons.append([Button("⬅️ بازگشت", data="acc:api")])
    return rtl("\n".join(lines)), buttons


def ask_email() -> Screen:
    return rtl(
        "📧 ایمیلت را بنویس.\n\n"
        "با همین می‌توانی از وب وارد شوی، و اگر پیام‌رسانت را از دست دادی "
        "حسابت را برگردانی."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_phone() -> Screen:
    return rtl(
        "📱 شماره‌ات را بنویس.\n\nمثلاً: 09121234567"
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_current_password() -> Screen:
    return rtl(
        "🔑 اول رمز فعلی را بنویس.\n\n"
        "پیامت بلافاصله پاک می‌شود."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_new_password(changing: bool) -> Screen:
    what = "رمز تازه" if changing else "رمزی که می‌خواهی"
    return rtl(
        f"🔑 {what} را بنویس.\n\n"
        "دست‌کم 8 نویسه.\n"
        "پیامت بلافاصله پاک می‌شود، ولی جای امنی نگهش دار."
    ), [[Button("⬅️ انصراف", data="acc:panel")]]


def ask_display_name(current: str) -> Screen:
    return rtl(f"✏️ نام تازه چه باشد؟\n\nالان: {current}"), [
        [Button("⬅️ انصراف", data="acc:panel")]
    ]


def ask_timezone(current: str) -> Screen:
    return rtl(
        f"🕐 منطقهٔ زمانی\n\nالان: {current}\n\n"
        "این ساعتی را تعیین می‌کند که خلاصهٔ روزانه به دستت می‌رسد."
    ), [
        [Button("تهران", data="acc:tzset:Asia/Tehran")],
        [Button("دبی", data="acc:tzset:Asia/Dubai"),
         Button("استانبول", data="acc:tzset:Europe/Istanbul")],
        [Button("لندن", data="acc:tzset:Europe/London"),
         Button("برلین", data="acc:tzset:Europe/Berlin")],
        [Button("تورنتو", data="acc:tzset:America/Toronto")],
        [Button("⬅️ بازگشت", data="acc:panel")],
    ]


def session_list(sessions) -> Screen:
    """Where this account is signed in, so a surprise can be noticed."""

    rows = list(sessions)
    if not rows:
        return rtl(
            "🖥 هیچ نشست فعالی نداری.\n\n"
            "نشست وقتی ساخته می‌شود که از وب یا API وارد شوی."
        ), [[Button("⬅️ بازگشت", data="acc:panel")]]

    lines = ["🖥 نشست‌های فعال:", ""]
    for row in rows[:10]:
        where = row.ip_address or "نامشخص"
        agent = (row.user_agent or "")[:40] or "نامشخص"
        lines.append(f"• {jalali.to_text(row.created_at.date())} — {where}\n  {agent}")

    lines += ["", "اگر چیزی این‌جا را نمی‌شناسی، همه را خارج کن و رمزت را عوض کن."]
    return rtl("\n".join(lines)), [
        [Button("🚪 خروج از همهٔ نشست‌ها", data="acc:signout")],
        [Button("⬅️ بازگشت", data="acc:panel")],
    ]


CLOSE_WORD = "حذف"


def confirm_close(preview) -> Screen:
    """Say exactly what will be destroyed before asking anyone to agree to it.

    "Are you sure?" is a useless question when the person cannot see what they
    are agreeing to.
    """
    if preview.blocked:
        return rtl(
            "🚫 هنوز نمی‌شود\n\n"
            "این دفترها عضو دیگری دارند و مال تو تنها نیستند:\n"
            + "\n".join(f"  • {name}" for name in preview.books_to_hand_over)
            + "\n\nاول هرکدام را به یکی از اعضایش واگذار کن، بعد دوباره بیا."
        ), [[Button("⬅️ بازگشت", data="acc:panel")]]

    lines = ["⚠️ حذف حساب", ""]
    if preview.books_to_delete:
        lines.append("این دفترها با همهٔ تراکنش‌هایشان پاک می‌شوند:")
        lines += [f"  • {name}" for name in preview.books_to_delete]
        lines.append("")
    if preview.other_books_left:
        lines.append(
            f"از {preview.other_books_left} دفتر دیگر بیرون می‌آیی، ولی آن دفترها "
            "می‌مانند."
        )
        lines.append("")
    lines += [
        "ایمیل، شماره، رمز و پیام‌رسان‌های متصلت پاک می‌شوند و دیگر نمی‌توانی "
        "وارد شوی.",
        "",
        "اگر در دفتر کسِ دیگری تراکنشی ثبت کرده باشی، آن تراکنش می‌ماند — "
        "چون پول واقعاً جابه‌جا شده — ولی دیگر نام تو را ندارد.",
        "",
        "این کار برگشت ندارد.",
    ]
    return rtl("\n".join(lines)), [
        [Button("🗑 می‌دانم، حذف کن", data="acc:closeok")],
        [Button("⬅️ منصرف شدم", data="acc:panel")],
    ]


def ask_close_word() -> Screen:
    return rtl(
        f"برای تأیید نهایی کلمهٔ «{CLOSE_WORD}» را بنویس.\n\n"
        "هر چیز دیگری بنویسی، انصراف حساب می‌شود."
    ), [[Button("⬅️ منصرف شدم", data="acc:panel")]]


def account_closed(removed: bool) -> Screen:
    """The last screen this account ever sees."""
    if removed:
        text = (
            "حسابت پاک شد.\n\n"
            "چیزی از تو نمانده. اگر روزی برگردی، از صفر شروع می‌کنی."
        )
    else:
        text = (
            "حسابت بسته شد.\n\n"
            "همهٔ اطلاعات شخصی‌ات پاک شد. تراکنش‌هایی که در دفتر دیگران ثبت "
            "کرده بودی مانده‌اند، چون آن پول واقعاً جابه‌جا شده — ولی دیگر به "
            "تو وصل نیستند."
        )
    return rtl("👋 " + text), [[Button("شروع دوباره", data="acc:create")]]


def identity_list(identities: Iterable[Identity], current: Provider) -> Screen:
    rows = list(identities)
    lines = ["🔗 حساب‌های متصل:", ""]

    for identity in rows:
        label = PROVIDER_LABELS.get(identity.provider, identity.provider.value)
        who = identity.external_username or identity.external_id
        here = " ← همین‌جا" if identity.provider is current else ""
        lines.append(f"• {label}: {who}{here}")

    missing = [p for p in PROVIDER_LABELS if p is not Provider.WEB and
               p not in {i.provider for i in rows}]
    if missing:
        lines += ["", "وصل‌نشده: " + "، ".join(PROVIDER_LABELS[p] for p in missing)]

    lines += ["", "برای وصل‌کردن یک پیام‌رسان دیگر، از پنل وب اقدام کن."]
    return rtl("\n".join(lines)), [[Button("⬅️ بازگشت", data="nav:home")]]


def ask_login_destination() -> Screen:
    return rtl("ایمیل یا شمارهٔ حساب مقصد را بفرست.\n"
               "کد به پیام‌رسان از قبل متصلِ حساب مقصد در همین نرم‌افزار ارسال می‌شود.\n"
               "دفترهای دو حساب ادغام نمی‌شوند."), [[Button("↩️ انصراف", data="acc:panel")]]


def ask_login_code() -> Screen:
    return rtl("اگر حساب مقصد در همین پیام‌رسان متصل باشد، کد ورود برایش ارسال می‌شود.\n"
               "کد را اینجا بفرست؛ اعتبار آن 5 دقیقه است."), [[Button("↩️ انصراف", data="acc:panel")]]


def login_proof(code) -> Screen:
    return rtl(f"🔐 کد ورود به حساب کسب‌بوک: {code}\nاعتبار: 5 دقیقه.\n"
               "فقط در ربات رسمی یا API رسمی کسب‌بوک وارد کن. اگر درخواست نداده‌ای، این پیام را نادیده بگیر."), []
