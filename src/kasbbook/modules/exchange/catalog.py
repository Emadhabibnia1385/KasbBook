"""The currencies a book can hold or be kept in.

Pure data, so a screen can name a currency without importing anything that talks
to a database. The fiat rows were generated once from CLDR (Babel 2.18: every
currency that is legal tender somewhere today, with its Persian name and
symbol) and are committed rather than read at run time, because the production
virtualenv does not carry Babel and a name must not change under a deploy.

IRT (toman) is not an ISO code but is what Iranian books are kept in, so it is
added by hand. The crypto rows are a short curated list, not an index: each
code has to fit the `book_currencies.code` column (8 characters).
"""

from __future__ import annotations

from dataclasses import dataclass


FIAT = "fiat"
CRYPTO = "crypto"
METAL = "metal"


@dataclass(frozen=True)
class Currency:
    code: str
    name: str
    symbol: str
    kind: str
    region: str = ""


# What a person looks for first. The picker shows these above the rest.
POPULAR = ("IRT", "IRR", "USD", "EUR", "GBP", "AED", "TRY", "USDT", "BTC", "ETH", "TON", "TRX")


_HAND = (
    Currency("IRT", "تومان", "تومان", FIAT, "ایران"),
    Currency("USDT", "تتر", "USDT", CRYPTO),
    Currency("USDC", "یواس‌دی‌کوین", "USDC", CRYPTO),
    Currency("BTC", "بیت‌کوین", "BTC", CRYPTO),
    Currency("ETH", "اتریوم", "ETH", CRYPTO),
    Currency("BNB", "بایننس‌کوین", "BNB", CRYPTO),
    Currency("SOL", "سولانا", "SOL", CRYPTO),
    Currency("XRP", "ریپل", "XRP", CRYPTO),
    Currency("TON", "تون", "TON", CRYPTO),
    Currency("TRX", "ترون", "TRX", CRYPTO),
    Currency("DOGE", "دوج‌کوین", "DOGE", CRYPTO),
    Currency("LTC", "لایت‌کوین", "LTC", CRYPTO),
    Currency("ADA", "کاردانو", "ADA", CRYPTO),
    Currency("DOT", "پولکادات", "DOT", CRYPTO),
    Currency("LINK", "چین‌لینک", "LINK", CRYPTO),
    Currency("AVAX", "آوالانچ", "AVAX", CRYPTO),
    Currency("BCH", "بیت‌کوین کش", "BCH", CRYPTO),
    Currency("XLM", "استلار", "XLM", CRYPTO),
    Currency("ATOM", "کازماس", "ATOM", CRYPTO),
    Currency("DAI", "دای", "DAI", CRYPTO),
    Currency("SHIB", "شیبا", "SHIB", CRYPTO),
    Currency("NOT", "نات‌کوین", "NOT", CRYPTO),
)


_ISO = (
    Currency("AED", "درهم امارات متحدهٔ عربی", "AED", FIAT, "امارات متحدهٔ عربی"),
    Currency("AFN", "افغانی افغانستان", "؋", FIAT, "افغانستان"),
    Currency("ALL", "لک آلبانی", "ALL", FIAT, "آلبانی"),
    Currency("AMD", "درام ارمنستان", "AMD", FIAT, "ارمنستان"),
    Currency("AOA", "کوانزای آنگولا", "AOA", FIAT, "آنگولا"),
    Currency("ARS", "پزوی آرژانتین", "ARS", FIAT, "آرژانتین"),
    Currency("AUD", "دلار استرالیا", "A$", FIAT, "چند کشور"),
    Currency("AWG", "فلورین آروبا", "AWG", FIAT, "آروبا"),
    Currency("AZN", "منات جمهوری آذربایجان", "AZN", FIAT, "جمهوری آذربایجان"),
    Currency("BAM", "مارک تبدیل\u200cپذیر بوسنی و هرزگوین", "BAM", FIAT, "بوسنی و هرزگوین"),
    Currency("BBD", "دلار باربادوس", "BBD", FIAT, "باربادوس"),
    Currency("BDT", "تاکای بنگلادش", "BDT", FIAT, "بنگلادش"),
    Currency("BGN", "لو بلغارستان", "BGN", FIAT, "بلغارستان"),
    Currency("BHD", "دینار بحرین", "BHD", FIAT, "بحرین"),
    Currency("BIF", "فرانک بوروندی", "BIF", FIAT, "بوروندی"),
    Currency("BMD", "دلار برمودا", "BMD", FIAT, "برمودا"),
    Currency("BND", "دلار برونئی", "BND", FIAT, "برونئی"),
    Currency("BOB", "بولیویانوی بولیوی", "BOB", FIAT, "بولیوی"),
    Currency("BRL", "رئال برزیل", "R$", FIAT, "برزیل"),
    Currency("BSD", "دلار باهاما", "BSD", FIAT, "باهاما"),
    Currency("BTN", "انگولتروم بوتان", "BTN", FIAT, "بوتان"),
    Currency("BWP", "پولای بوتسوانا", "BWP", FIAT, "بوتسوانا"),
    Currency("BYN", "روبل بلاروس", "BYN", FIAT, "بلاروس"),
    Currency("BZD", "دلار بلیز", "BZD", FIAT, "بلیز"),
    Currency("CAD", "دلار کانادا", "$CA", FIAT, "کانادا"),
    Currency("CDF", "فرانک کنگو", "CDF", FIAT, "کنگو - کینشاسا"),
    Currency("CHF", "فرانک سوئیس", "CHF", FIAT, "سوئیس، لیختن\u200cاشتاین"),
    Currency("CLP", "پزوی شیلی", "CLP", FIAT, "شیلی"),
    Currency("CNY", "یوآن چین", "¥CN", FIAT, "چین"),
    Currency("COP", "پزوی کلمبیا", "COP", FIAT, "کلمبیا"),
    Currency("CRC", "کولون کاستاریکا", "CRC", FIAT, "کاستاریکا"),
    Currency("CUP", "پزوی کوبا", "CUP", FIAT, "کوبا"),
    Currency("CVE", "اسکودوی کیپ\u200cورد", "CVE", FIAT, "کیپ\u200cورد"),
    Currency("CZK", "کورونای جمهوری چک", "CZK", FIAT, "چک"),
    Currency("DJF", "فرانک جیبوتی", "DJF", FIAT, "جیبوتی"),
    Currency("DKK", "کرون دانمارک", "DKK", FIAT, "چند کشور"),
    Currency("DOP", "پزوی جمهوری دومینیکن", "DOP", FIAT, "جمهوری دومینیکن"),
    Currency("DZD", "دینار الجزایر", "DZD", FIAT, "الجزایر"),
    Currency("EGP", "پوند مصر", "EGP", FIAT, "مصر"),
    Currency("ERN", "ناکفای اریتره", "ERN", FIAT, "اریتره"),
    Currency("ETB", "بیر اتیوپی", "ETB", FIAT, "اتیوپی"),
    Currency("EUR", "یورو", "€", FIAT, "چند کشور"),
    Currency("FJD", "دلار فیجی", "FJD", FIAT, "فیجی"),
    Currency("FKP", "پوند جزایر فالکلند", "FKP", FIAT, "جزایر فالکلند"),
    Currency("GBP", "پوند بریتانیا", "£", FIAT, "چند کشور"),
    Currency("GEL", "لاری گرجستان", "GEL", FIAT, "گرجستان"),
    Currency("GHS", "سدی غنا", "GHS", FIAT, "غنا"),
    Currency("GIP", "پوند جبل\u200cالطارق", "GIP", FIAT, "جبل\u200cالطارق"),
    Currency("GMD", "دالاسی گامبیا", "GMD", FIAT, "گامبیا"),
    Currency("GNF", "فرانک گینه", "GNF", FIAT, "گینه"),
    Currency("GTQ", "کتزال گواتمالا", "GTQ", FIAT, "گواتمالا"),
    Currency("GYD", "دلار گویانا", "GYD", FIAT, "گویان"),
    Currency("HKD", "دلار هنگ\u200cکنگ", "$HK", FIAT, "هنگ\u200cکنگ، منطقهٔ ویژهٔ اداری چین"),
    Currency("HNL", "لمپیرای هندوراس", "HNL", FIAT, "هندوراس"),
    Currency("HTG", "گورد هائیتی", "HTG", FIAT, "هائیتی"),
    Currency("HUF", "فورینت مجارستان", "HUF", FIAT, "مجارستان"),
    Currency("IDR", "روپیهٔ اندونزی", "IDR", FIAT, "اندونزی"),
    Currency("ILS", "شِکِل جدید اسرائیل", "₪", FIAT, "اسرائیل، سرزمین\u200cهای فلسطینی"),
    Currency("INR", "روپیهٔ هند", "₹", FIAT, "بوتان، هند"),
    Currency("IQD", "دینار عراق", "IQD", FIAT, "عراق"),
    Currency("IRR", "ریال", "ریال", FIAT, "ایران"),
    Currency("ISK", "کرونای ایسلند", "ISK", FIAT, "ایسلند"),
    Currency("JMD", "دلار جامائیکا", "JMD", FIAT, "جامائیکا"),
    Currency("JOD", "دینار اردن", "JOD", FIAT, "اردن، سرزمین\u200cهای فلسطینی"),
    Currency("JPY", "ین ژاپن", "¥", FIAT, "ژاپن"),
    Currency("KES", "شیلینگ کنیا", "KES", FIAT, "کنیا"),
    Currency("KGS", "سوم قرقیزستان", "KGS", FIAT, "قرقیزستان"),
    Currency("KHR", "ری\u200cیل کامبوج", "KHR", FIAT, "کامبوج"),
    Currency("KMF", "فرانک کومورو", "KMF", FIAT, "کومور"),
    Currency("KPW", "وون کرهٔ شمالی", "KPW", FIAT, "کرهٔ شمالی"),
    Currency("KRW", "وون کرهٔ جنوبی", "₩", FIAT, "کرهٔ جنوبی"),
    Currency("KWD", "دینار کویت", "KWD", FIAT, "کویت"),
    Currency("KYD", "دلار جزایر کِیمن", "KYD", FIAT, "جزایر کِیمن"),
    Currency("KZT", "تنگهٔ قزاقستان", "KZT", FIAT, "قزاقستان"),
    Currency("LAK", "کیپ لائوس", "LAK", FIAT, "لائوس"),
    Currency("LBP", "لیرهٔ لبنان", "LBP", FIAT, "لبنان"),
    Currency("LKR", "روپیهٔ سری\u200cلانکا", "LKR", FIAT, "سری\u200cلانکا"),
    Currency("LRD", "دلار لیبریا", "LRD", FIAT, "لیبریا"),
    Currency("LSL", "لوتی لسوتو", "LSL", FIAT, "لسوتو"),
    Currency("LYD", "دینار لیبی", "LYD", FIAT, "لیبی"),
    Currency("MAD", "درهم مراکش", "MAD", FIAT, "صحرای غربی، مراکش"),
    Currency("MDL", "لئوی مولداوی", "MDL", FIAT, "مولداوی"),
    Currency("MGA", "آریاری مالاگاسی", "MGA", FIAT, "ماداگاسکار"),
    Currency("MKD", "دینار مقدونیه", "MKD", FIAT, "مقدونیهٔ شمالی"),
    Currency("MMK", "کیات میانمار", "MMK", FIAT, "میانمار (برمه)"),
    Currency("MNT", "توگریک مغولستان", "MNT", FIAT, "مغولستان"),
    Currency("MOP", "پاتاکای ماکائو", "MOP", FIAT, "ماکائو، منطقهٔ ویژهٔ اداری چین"),
    Currency("MRU", "اوگوئیای موریتانی", "MRU", FIAT, "موریتانی"),
    Currency("MUR", "روپیهٔ موریس", "MUR", FIAT, "موریس"),
    Currency("MVR", "روپیهٔ مالدیو", "MVR", FIAT, "مالدیو"),
    Currency("MWK", "کواچای مالاوی", "MWK", FIAT, "مالاوی"),
    Currency("MXN", "پزوی مکزیک", "$MX", FIAT, "مکزیک"),
    Currency("MYR", "رینگیت مالزی", "MYR", FIAT, "مالزی"),
    Currency("MZN", "متیکال موزامبیک", "MZN", FIAT, "موزامبیک"),
    Currency("NAD", "دلار نامیبیا", "NAD", FIAT, "نامیبیا"),
    Currency("NGN", "نایرای نیجریه", "NGN", FIAT, "نیجریه"),
    Currency("NIO", "کوردوبای نیکاراگوئه", "NIO", FIAT, "نیکاراگوئه"),
    Currency("NOK", "کرون نروژ", "NOK", FIAT, "چند کشور"),
    Currency("NPR", "روپیهٔ نپال", "NPR", FIAT, "نپال"),
    Currency("NZD", "دلار زلاند نو", "$NZ", FIAT, "چند کشور"),
    Currency("OMR", "ریال عمان", "OMR", FIAT, "عمان"),
    Currency("PAB", "بالبوای پاناما", "PAB", FIAT, "پاناما"),
    Currency("PEN", "سول پرو", "PEN", FIAT, "پرو"),
    Currency("PGK", "کینای پاپوا گینهٔ نو", "PGK", FIAT, "پاپوا گینهٔ نو"),
    Currency("PHP", "پزوی فیلیپین", "PHP", FIAT, "فیلیپین"),
    Currency("PKR", "روپیهٔ پاکستان", "PKR", FIAT, "پاکستان"),
    Currency("PLN", "زلوتی لهستان", "PLN", FIAT, "لهستان"),
    Currency("PYG", "گوارانی پاراگوئه", "PYG", FIAT, "پاراگوئه"),
    Currency("QAR", "ریال قطر", "QAR", FIAT, "قطر"),
    Currency("RON", "لئوی رومانی", "RON", FIAT, "رومانی"),
    Currency("RSD", "دینار صربستان", "RSD", FIAT, "صربستان"),
    Currency("RUB", "روبل روسیه", "RUB", FIAT, "روسیه"),
    Currency("RWF", "فرانک رواندا", "RWF", FIAT, "رواندا"),
    Currency("SAR", "ریال سعودی", "SAR", FIAT, "عربستان سعودی"),
    Currency("SBD", "دلار جزایر سلیمان", "SBD", FIAT, "جزایر سلیمان"),
    Currency("SCR", "روپیهٔ سیشل", "SCR", FIAT, "سیشل"),
    Currency("SDG", "پوند سودان", "SDG", FIAT, "سودان"),
    Currency("SEK", "کرون سوئد", "SEK", FIAT, "سوئد"),
    Currency("SGD", "دلار سنگاپور", "SGD", FIAT, "سنگاپور"),
    Currency("SHP", "پوند سنت هلن", "SHP", FIAT, "جزایر آسنسیون، سنت هلن"),
    Currency("SLE", "لئون سیرالئون", "SLE", FIAT, "سیرالئون"),
    Currency("SOS", "شیلینگ سومالی", "SOS", FIAT, "سومالی"),
    Currency("SRD", "دلار سورینام", "SRD", FIAT, "سورینام"),
    Currency("SSP", "پوند سودان جنوبی", "SSP", FIAT, "سودان جنوبی"),
    Currency("STN", "دوبرای سائوتومه و پرنسیپ", "STN", FIAT, "سائوتومه و پرینسیپ"),
    Currency("SYP", "لیرهٔ سوریه", "SYP", FIAT, "سوریه"),
    Currency("SZL", "لیلانگنی سوازیلند", "SZL", FIAT, "اسواتینی"),
    Currency("THB", "بات تایلند", "฿", FIAT, "تایلند"),
    Currency("TJS", "سامانی تاجیکستان", "TJS", FIAT, "تاجیکستان"),
    Currency("TMT", "منات ترکمنستان", "TMT", FIAT, "ترکمنستان"),
    Currency("TND", "دینار تونس", "TND", FIAT, "تونس"),
    Currency("TOP", "پاآنگای تونگا", "TOP", FIAT, "تونگا"),
    Currency("TRY", "لیرهٔ ترکیه", "TRY", FIAT, "ترکیه"),
    Currency("TTD", "دلار ترینیداد و توباگو", "TTD", FIAT, "ترینیداد و توباگو"),
    Currency("TWD", "دلار جدید تایوان", "NT$", FIAT, "تایوان"),
    Currency("TZS", "شیلینگ تانزانیا", "TZS", FIAT, "تانزانیا"),
    Currency("UAH", "هریونیای اوکراین", "UAH", FIAT, "اوکراین"),
    Currency("UGX", "شیلینگ اوگاندا", "UGX", FIAT, "اوگاندا"),
    Currency("USD", "دلار آمریکا", "$", FIAT, "چند کشور"),
    Currency("UYU", "پزوی اوروگوئه", "UYU", FIAT, "اروگوئه"),
    Currency("UZS", "سوم ازبکستان", "UZS", FIAT, "ازبکستان"),
    Currency("VES", "بولیوار ونزوئلا", "VES", FIAT, "ونزوئلا"),
    Currency("VND", "دانگ ویتنام", "₫", FIAT, "ویتنام"),
    Currency("VUV", "واتوی وانوواتو", "VUV", FIAT, "وانواتو"),
    Currency("WST", "تالای ساموا", "WST", FIAT, "ساموآ"),
    Currency("XAF", "فرانک CFA مرکز افریقا", "FCFA", FIAT, "چند کشور"),
    Currency("XCD", "دلار شرق کارائیب", "$EC", FIAT, "چند کشور"),
    Currency("XCG", "XCG", "Cg.", FIAT, "کوراسائو، سنت مارتن"),
    Currency("XOF", "فرانک CFA غرب افریقا", "فرانک CFA", FIAT, "چند کشور"),
    Currency("XPF", "فرانک اقیانوسیه", "CFPF", FIAT, "چند کشور"),
    Currency("YER", "ریال یمن", "YER", FIAT, "یمن"),
    Currency("ZAR", "راند افریقای جنوبی", "ZAR", FIAT, "چند کشور"),
    Currency("ZMW", "کواچای زامبیا", "ZMW", FIAT, "زامبیا"),
    Currency("ZWG", "ZWG", "ZWG", FIAT, "زیمبابوه"),
)


# Gold, coins and metals as units a book can hold and count in: a gold trader's stock is grams, not toman.
# Each is priced in toman by the metal feeds (see `METAL_INSTRUMENT`), which is what the web quotes through.
_METALS = (
    Currency("GOLD18", "طلای ۱۸ عیار (گرم)", "گرم", METAL, "بازار ایران"),
    Currency("GOLD24", "طلای ۲۴ عیار (گرم)", "گرم", METAL, "بازار ایران"),
    Currency("MESGHAL", "مثقال طلا", "مثقال", METAL, "بازار ایران"),
    Currency("EMAMI", "سکهٔ امامی", "سکه", METAL, "بازار ایران"),
    Currency("BAHAR", "سکهٔ بهار آزادی", "سکه", METAL, "بازار ایران"),
    Currency("NIM", "نیم‌سکه", "نیم‌سکه", METAL, "بازار ایران"),
    Currency("ROB", "ربع‌سکه", "ربع‌سکه", METAL, "بازار ایران"),
    Currency("GRAMI", "سکهٔ گرمی", "سکه", METAL, "بازار ایران"),
    Currency("SILVER", "نقرهٔ ۹۹۹ (گرم)", "گرم", METAL, "بازار ایران"),
    Currency("XAU", "اونس طلا", "اونس", METAL, "بازار جهانی"),
    Currency("XAG", "اونس نقره", "اونس", METAL, "بازار جهانی"),
    Currency("XPT", "اونس پلاتین", "اونس", METAL, "بازار جهانی"),
    Currency("XPD", "اونس پالادیوم", "اونس", METAL, "بازار جهانی"),
)

# Which price (see `modules/portfolio/catalog.py`) values each of them.
METAL_INSTRUMENT = {
    "GOLD18": "gold18", "GOLD24": "gold24", "MESGHAL": "mesghal", "EMAMI": "coin_emami",
    "BAHAR": "coin_bahar", "NIM": "coin_half", "ROB": "coin_quarter", "GRAMI": "coin_gram",
    "SILVER": "silver", "XAU": "XAU", "XAG": "XAG", "XPT": "XPT", "XPD": "XPD",
}

CATALOG: tuple[Currency, ...] = _HAND + _METALS + _ISO
BY_CODE = {c.code: c for c in CATALOG}


def _fold(text: str) -> str:
    """Case, Arabic yeh/kaf and digits folded, so «دلار», «دلار», «usd» and «USD» meet."""
    table = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "‌": " "})
    return text.translate(table).casefold().strip()


def search(query: str, limit: int = 8) -> list:
    """Currencies whose name, code, symbol or country contains every word of the query, best first.

    An exact code first, then popular currencies, then names that start with the word, then the rest.
    """
    words = [w for w in _fold(query).split() if w]
    if not words:
        return []
    scored = []
    for position, currency in enumerate(CATALOG):
        haystack = _fold(f"{currency.name} {currency.code} {currency.symbol} {currency.region}")
        if not all(w in haystack for w in words):
            continue
        first = words[0]
        # An exact code first, then the currencies people actually use that match, then names that start
        # with the word: «دلار» is a dozen currencies and the first one should be the American.
        rank = (
            0 if currency.code.casefold() == first
            else 1 if currency.code in POPULAR
            else 2 if _fold(currency.name).startswith(first)
            else 3
        )
        scored.append((rank, position, currency))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]]
