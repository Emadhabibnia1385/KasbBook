// Words of the live clock, the price widgets and the on/off switches; spread into `t` in fa.ts.
export const marketStrings = {
	clock: {
		// Read once by a screen reader instead of the seconds, which would be announced forever.
		label: "تاریخ و ساعت اکنون",
		clockWord: "ساعت",
	},
	market: {
		title: "قیمت لحظه‌ای",
		lead: "قیمت بازار ارز دیجیتال به تومان؛ هر یک دقیقه تازه می‌شود.",
		tickerLabel: "قیمت لحظه‌ای",
		pairs: "قیمت‌ها",
		sourceLabel: "منبع",
		sources: { swapwallet: "سواپ‌ولت" } as Record<string, string>,
		assets: {
			USDT: "تتر",
			BTC: "بیت‌کوین",
			ETH: "اتریوم",
			TON: "تون",
			TRX: "ترون",
			BNB: "بی‌ان‌بی",
		} as Record<string, string>,
		loading: "در حال گرفتن قیمت‌ها…",
		empty: "قیمتی برای نمایش نیست.",
		unavailable: "قیمت لحظه‌ای فعلاً در دسترس نیست.",
		unavailableShort: "قیمت در دسترس نیست",
		retry: "تلاش دوباره",
		refreshFailed: "تازه‌سازی انجام نشد؛ آخرین قیمت‌های گرفته‌شده را می‌بینی.",
		// «۳ دقیقه پیش» is built from these, so a number is never left to a template with the wrong plural.
		age: {
			now: "همین حالا",
			seconds: "ثانیه پیش",
			minutes: "دقیقه پیش",
			hours: "ساعت پیش",
			days: "روز پیش",
		},
		updated: "به‌روزرسانی",
		staleTitle: "قیمت‌ها قدیمی‌اند",
		staleBody:
			"منبع قیمت جواب نمی‌دهد و این‌ها آخرین قیمت‌های معتبرند. پیش از تصمیم گرفتن با این اعداد، قیمت را جای دیگری هم ببین.",
		staleShort: "قدیمی",
	},
	// The rate beside the payroll pay form's own field.
	rateNote: {
		source: "نرخ بازار از",
		useMarket: "استفاده از نرخ بازار",
		stale: "این نرخ قدیمی است؛ پیش از ثبت، آن را بررسی کن.",
		missing: "نرخ بازار برای این ارز نیست؛ نرخ را خودت بنویس.",
		loading: "در حال گرفتن نرخ بازار…",
		failed: "نرخ بازار گرفته نشد؛ نرخ را خودت بنویس.",
		editable: "می‌توانی آن را تغییر بدهی؛ نرخی که اینجا بماند ثبت می‌شود.",
	},
	// The on/off switches of the funds tab.
	switches: {
		fund: "برداشت از این صندوق",
		fundHint:
			"خاموش باشد، از دوره‌هایی که از این پس حساب می‌شوند چیزی برنمی‌دارد. قاعده‌هایش همان می‌مانند و با روشن‌کردن دوباره برمی‌گردند.",
		rule: "اعمال این قاعده",
		ruleHint:
			"خاموش باشد، در هیچ دورهٔ تازه‌ای حساب نمی‌شود، با هر تاریخی. تاریخ‌هایش دست نمی‌خورد و با روشن‌کردن دوباره همان است که بود.",
		lockedNote: "دوره‌های پرداخت‌شده یا قفل‌شده همان که بودند می‌مانند.",
		fundTurnOn: "روشن کردن صندوق",
		fundTurnOff: "خاموش کردن صندوق",
		ruleTurnOn: "روشن کردن",
		ruleTurnOff: "خاموش کردن",
		fundOn: "صندوق روشن شد",
		fundOff: "صندوق خاموش شد",
		ruleOn: "قاعده روشن شد",
		ruleOff: "قاعده خاموش شد",
		ended: "پایان‌یافته",
		stopDiffers:
			"«توقف از امروز» فرق دارد: برای قاعده تاریخ پایان می‌گذارد، برگشت ندارد و دوره‌های گذشته را دست نمی‌زند.",
	},
	tickerSettings: {
		title: "ارزهای نوار قیمت",
		description:
			"این ارزها بالای صفحه و در کارت قیمت لحظه‌ای نشان داده می‌شوند. تا ۶ ارز، از هر ارزی در فهرست.",
		add: "افزودن ارز",
		already: "در نوار هست",
		reset: "برگرداندن به پیش‌فرض",
		full: "حداکثر ۶ ارز",
	},
};
