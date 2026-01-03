````html
<div align="center">
<img src="./KasbBook_LOGO.png" alt="KasbBook Logo" width="260"/>

# 📊 KasbBook

### مدیریت مالی کسب‌وکار در تلگرام

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![Stars](https://img.shields.io/github/stars/Emadhabibnia1385/KasbBook?style=for-the-badge&logo=github)](https://github.com/Emadhabibnia1385/KasbBook/stargazers)

**یک ربات تلگرام متن‌باز برای ثبت درآمد/هزینه، مدیریت دسته‌بندی‌ها و دریافت گزارش‌های روزانه، ماهانه و سالانه**

[نصب سریع](#-نصب-سریع) • [ویژگی‌ها](#-ویژگیها) • [راهنمای استفاده](#-راهنمای-استفاده) • [پشتیبانی](#-پشتیبانی)

---

</div>

## 📖 درباره KasbBook

KasbBook یک ربات تلگرام کاملاً فارسی برای مدیریت مالی کسب‌وکارهای کوچک و فروشندگان است.  
با این ربات می‌توانید درآمدها و هزینه‌ها را سریع ثبت کنید، دسته‌بندی بسازید و گزارش‌های دقیق روزانه/ماهانه/سالانه دریافت کنید.

### 🎯 مناسب برای:
- 🏪 فروشگاه‌ها و غرفه‌ها
- 👤 فروشندگان و فریلنسرها
- 💼 کسب‌وکارهای کوچک
- 🧾 ثبت ساده حساب‌وکتاب روزانه

---

## ✨ ویژگی‌ها

<table>
<tr>
<td width="25%" align="center">

### 🧾 ثبت تراکنش
✅ درآمد کاری  
✅ هزینه کاری  
✅ هزینه شخصی  
✅ ثبت سریع و دقیق

</td>
<td width="25%" align="center">

### 🎨 رابط کاربری
✅ کاملاً فارسی  
✅ دکمه‌های شیشه‌ای  
✅ منوهای ساده  
✅ تجربه کاربری روان

</td>
<td width="25%" align="center">

### 📊 گزارش‌ها
✅ گزارش روزانه  
✅ گزارش ماهانه  
✅ گزارش سالانه  
✅ محاسبه سود و پس‌انداز

</td>
<td width="25%" align="center">

### 🗄 بکاپ و مدیریت
✅ بکاپ دستی دیتابیس  
✅ بکاپ خودکار (زمان‌بندی)  
✅ ارسال به آیدی/کانال  
✅ بازیابی دیتابیس

</td>
</tr>
</table>

---

## 🤖 Demo Bot
- Bot: https://t.me/KasbBook_BOT

## 📣 Telegram Channel
- Channel: https://t.me/KasbBook

## 👨‍💻 Developer
- https://t.me/EmadHabibnia

---

## 🚀 نصب سریع

### نصب خودکار (پیشنهادی) ⚡

روی سرور **Ubuntu** فقط این دستورات را اجرا کنید:

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/Emadhabibnia1385/KasbBook/main/install.sh
chmod +x install.sh
sudo ./install.sh
````

> **نکته:** برای اجرای دستور بالا نیاز به دسترسی root دارید.

---

## 📱 راهنمای استفاده

### دریافت اطلاعات لازم

#### 1) دریافت Bot Token:

1. به [@BotFather](https://t.me/BotFather) پیام دهید
2. دستور `/newbot` را ارسال کنید
3. نام و یوزرنیم ربات را وارد کنید
4. توکن دریافتی را در `.env` قرار دهید

#### 2) دریافت Chat ID:

1. به [@userinfobot](https://t.me/userinfobot) پیام دهید
2. عدد `Id` را کپی کنید

---

## 🔧 تنظیمات (.env)

بعد از نصب، فایل `.env` را ویرایش کنید:

```bash
nano /opt/kasbbook/.env
```

نمونه:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_CHAT_ID=123456789
ADMIN_USERNAME=EmadHabibnia
```

> اگر هرکدام از متغیرها ست نشده باشد، ربات با **RuntimeError** اجرا نمی‌شود.

---

## 🎮 مدیریت سرویس

اگر نصب‌کننده را اجرا کرده باشید، سرویس به صورت systemd ساخته می‌شود.
می‌توانید با دستورات زیر مدیریت کنید:

```bash
# وضعیت ربات
systemctl status kasbbook

# شروع
systemctl start kasbbook

# توقف
systemctl stop kasbbook

# ریستارت
systemctl restart kasbbook

# لاگ زنده
journalctl -u kasbbook -f
```

---

## 📁 ساختار پروژه

```
KasbBook/
├── .env.example          # نمونه فایل تنظیمات
├── README.md            # مستندات پروژه
├── bot.py               # فایل اصلی ربات
├── install.sh           # اسکریپت نصب خودکار
└── requirements.txt     # وابستگی‌های پایتون
```

---

## 🗄 دیتابیس

دیتابیس اصلی پروژه:

* `KasbBook.db`

### حذف دیتابیس (ریست کامل)

اگر نیاز به ریست کامل دارید:

```bash
cd /opt/kasbbook
rm -f KasbBook.db
systemctl restart kasbbook
```

---

## 🐛 رفع مشکلات رایج

<details>
<summary><b>ربات استارت نمی‌شود</b></summary>

```bash
# بررسی لاگ‌ها
journalctl -u kasbbook -n 80

# بررسی فایل .env
cat /opt/kasbbook/.env

# تست دستی
cd /opt/kasbbook
source venv/bin/activate
python3 bot.py
```

</details>

<details>
<summary><b>خطای Invalid Token</b></summary>

توکن را از [@BotFather](https://t.me/BotFather) دوباره بگیرید و در `.env` قرار دهید، سپس:

```bash
systemctl restart kasbbook
```

</details>

<details>
<summary><b>ربات جواب نمی‌دهد</b></summary>

1. مطمئن شوید `ADMIN_CHAT_ID` درست است
2. آیدی خود را از [@userinfobot](https://t.me/userinfobot) دوباره بگیرید
3. ربات را ریستارت کنید:

```bash
systemctl restart kasbbook
```

</details>

---

## 🤝 مشارکت در پروژه

مشارکت شما در بهبود KasbBook خوش‌آمد است!

1. پروژه را Fork کنید
2. یک Branch جدید بسازید (`git checkout -b feature/amazing-feature`)
3. تغییرات را Commit کنید (`git commit -m 'Add amazing feature'`)
4. Push کنید (`git push origin feature/amazing-feature`)
5. Pull Request بسازید

---

## 📞 پشتیبانی

<div align="center">

[![Telegram](https://img.shields.io/badge/Developer-@EmadHabibnia-blue?style=for-the-badge\&logo=telegram)](https://t.me/EmadHabibnia)
[![Channel](https://img.shields.io/badge/Channel-@KasbBook-blue?style=for-the-badge\&logo=telegram)](https://t.me/KasbBook)

</div>

* 💬 **تلگرام:** [https://t.me/EmadHabibnia](https://t.me/EmadHabibnia)
* 📢 **کانال:** [https://t.me/KasbBook](https://t.me/KasbBook)

---

## ⭐ حمایت از پروژه

اگر KasbBook برای شما مفید بود:

* ⭐ به پروژه Star بدهید
* 🔀 آن را Fork کنید
* 📢 در کانال‌های خود معرفی کنید
* 💡 پیشنهادهای خود را ارسال کنید

---

<div align="center">

**ساخته شده با ❤️ توسط [Emad Habibnia](https://t.me/EmadHabibnia)**

</div>
```
