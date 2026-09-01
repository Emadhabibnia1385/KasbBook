# شروع

## روی سرور

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/scripts/install.sh | sudo bash
```

به دبیان یا اوبونتو نیاز داری، پایتون ۳٫۱۱ به بالا، و داکر اگر می‌خواهی نصب‌کننده
خودش پستگرس و ردیس را برایت بالا بیاورد.

سه چیز می‌پرسد: توکن ربات از [@BotFather](https://t.me/BotFather)، نام‌کاربری
ربات، و — اختیاری — نشانی https عمومی‌ای که این API روی آن سرو می‌شود. همان
آخری است که باعث می‌شود صفحهٔ API ربات به مستندات خودت پیوند بدهد، و اگر روزی
به وب‌هوک سوئیچ کنی لازم است. خالی بگذاری، به هیچ‌جا پیوند نمی‌دهد — که بهتر از
پیوند به جای مرده است.

بقیه را خودش می‌سازد — رمز دیتابیس، کلید امضا، راز مسیر وب‌هوک — چون **رازی که
آدم انتخابش کند رازی است که آدم می‌تواند حدسش بزند.**

پرسش‌ها از ترمینال تو خوانده می‌شوند نه از ورودی استاندارد، چون ورودی استاندارد
در `curl ... | bash` خودِ اسکریپت است. برای نصب بدون هیچ ترمینالی، جواب‌ها را
از محیط بده:

```bash
curl -fsSL https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/scripts/install.sh \
  | sudo TELEGRAM_BOT_TOKEN=... TELEGRAM_BOT_USERNAME=YourBot \
         KASBBOOK_API_URL=https://your.host bash
```

دوباره اجرا کردنش بی‌خطر است: نصب نیمه‌کاره را ترمیم می‌کند، `.env` موجود را
دست نمی‌زند، و هر چیزی را که کم دارد اضافه می‌کند.

وقتی تمام شد:

```
✓ kasbbook-bot is running
✓ kasbbook-api is running
✓ the API answers /readyz
```

اگر این را نگفت، پانزده خط آخر لاگ را چاپ می‌کند و با کد خطا بیرون می‌آید،
به‌جای اینکه ادعای موفقیت کند. [عیب‌یابی](troubleshooting.md) را ببین.

## روی لپ‌تاپ

برای اجرای تست‌ها نه داکر لازم است، نه پستگرس، نه توکن.

```bash
git clone https://github.com/Emadhabibnia1385/KasbBook.git
cd KasbBook
python3 -m venv venv
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest tests -q
```

برای اجرای واقعی ربات، توکن و یک دیتابیس لازم است. پیش‌فرض SQLite است، پس همین
کافی است:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_BOT_USERNAME=YourBot
export KASBBOOK_DATABASE_URL="sqlite+aiosqlite:///kasbbook.db"
./venv/bin/alembic upgrade head
./venv/bin/python apps/bot/runner.py
```

و API:

```bash
export KASBBOOK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
PYTHONPATH=src ./venv/bin/uvicorn --factory kasbbook.api.app:create_app --reload
```

بعد `http://127.0.0.1:8000/docs` را باز کن.

## اولین اجرا، از دید کاربر

**۱. بنویس `/start`.** ربات این حساب پیام‌رسان را نمی‌شناسد، پس یک کد یک‌بارمصرف
می‌دهد و می‌خواهد آن را ثبت کنی. همان کد است که یک حساب تلگرام را به یک حساب
کسب‌بوک **وصل** می‌کند، نه اینکه *خودش* آن حساب باشد — چرایی این تمایز در
[مدل داده](data-model.md) است.

**۲. یک دفتر بساز.** شخصی، کسب‌وکار، تیمی یا سازمانی. نوعش تزئینی نیست: دفتر
تیمی حقوق و سهم اعضا می‌گیرد، شخصی نمی‌گیرد، و دامنهٔ پیش‌فرض تراکنش از همان
تعیین می‌شود.

**۳. چیزی ثبت کن.** یا با دکمه‌ها پیش برو، یا فقط بنویس:

```
فروش ۲۵۰ک
```

درآمد، دستهٔ «فروش»، ۲۵۰٬۰۰۰. پشتش یک سند تراز نوشته شد؛ حالا `trial_balance()`
روی آن دفتر دو عدد برابر برمی‌گرداند.

**۴. گزارش بگیر.** گزارش‌ها جلالی‌اند. `۱۴۰۳-۰۵` یعنی مرداد ۱۴۰۳ — پیش از کوئری
به بازهٔ میلادی تبدیل می‌شود، پس دیتابیس هرگز مقدار جلالی نمی‌بیند و تو هرگز
میلادی.

## بعد چه چیزی را تنظیم کنیم

| | |
|---|---|
| **یادآورها** | خلاصهٔ روزانه در ساعتی که خودت انتخاب می‌کنی، به وقت خودت. پیش‌فرض روشن، ساعت ۲۱ — ابزار دفترداری‌ای که هیچ‌وقت اول حرف نزند، ابزاری است که یادت می‌رود بازش کنی. |
| **بودجه** | سقف برای هر دسته. ربات موقع نزدیک‌شدن هشدار می‌دهد، نه بعدش. |
| **قواعد تکرارشونده** | اجاره، حقوق، اشتراک. یک بار تعریف، سر موعد ثبت — و اگر ربات خواب بوده، جبران می‌کند. |
| **پیام‌رسان دوم** | بله یا روبیکا را از صفحهٔ حساب به همین حساب وصل کن. همان دفترها، برنامهٔ دیگر. |

## چه چیزی روی سرور کجاست

```
/opt/kasbbook/          کد، محیط پایتون، .env
/opt/kasbbook/deploy/   docker-compose.yml و deploy/.env
/var/backups/kasbbook/  چهارده پشتیبان آخر
/etc/systemd/system/    kasbbook-bot.service و kasbbook-api.service
```

```bash
journalctl -u kasbbook-bot -f      # ربات چه می‌کند
journalctl -u kasbbook-api -f      # API چه می‌کند
sudo /opt/kasbbook/scripts/update.sh
```
