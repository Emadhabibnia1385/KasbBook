const CACHE = "kasbbook-38d7a507ff";
const FILES = ["/assets/BottomSheet-B87T1qA-.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-Dq4fOJ1R.js","/assets/ConfirmDialog-OnY5MlXG.js","/assets/CurrencyPicker-C1DDzzZg.js","/assets/DataTable-BVBtBpST.js","/assets/DateTimeField-_JPgNzJS.js","/assets/DayField-et7ytyHm.js","/assets/ErrorState-CulsQfog.js","/assets/FilterChips-DrMLXw5_.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-DpDunUDO.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-CJ3Ezqhr.js","/assets/Notice-Di_8En44.js","/assets/PageHeader-DM9XHi4w.js","/assets/PayrollPage-CWr1Wa3y.js","/assets/SearchBox-CTvVfcMy.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-C-fadgA0.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-DDBbsR8e.js","/assets/SwitchField-DwWGNEei.js","/assets/TextField-fpQhjT71.js","/assets/_app-BCT0WuHZ.js","/assets/_app.account-DrGkHf1b.js","/assets/_app.books-DJLQlswd.js","/assets/_app.index-D5iilSvu.js","/assets/_app.more-aTzVcYKU.js","/assets/_app.planning-CtTcaT7I.js","/assets/_app.recurring-BC-haIbB.js","/assets/_app.reports-D2O8B0Rc.js","/assets/_app.team-C4cU5JFO.js","/assets/_app.team.funds-D40uKY2c.js","/assets/_app.team.index-CtNjczXa.js","/assets/_app.team.periods._periodId-DSiNUqf2.js","/assets/_app.team.periods.index-7MjZbNuZ.js","/assets/_app.team.shares-4L7-Y0uH.js","/assets/_app.transactions-BWCrWYyf.js","/assets/_app.wallet-CZJCUXYt.js","/assets/accent-299jXqvc.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-CnXl5sKQ.js","/assets/icons-JcburOYw.js","/assets/index-CU_ugHU3.css","/assets/index-x7h2crpp.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-DuPl8gxx.js","/assets/market-h7uCN0GJ.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations--B1-JrWl.js","/assets/queryDefaults-C8Cdmqsx.js","/assets/schemas-DuRJH2YM.js","/assets/shared-BmF6eidX.js","/assets/signOut-ohtXjn-P.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-COQeyJIS.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-l4LGBfBl.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-JK_RY-YM.js","/assets/useCatalog-BTSgH6H0.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-D0o2_m4e.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-xs0QuOJq.js","/assets/useTextField-Da2-IfxV.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
self.addEventListener("install", (event) => {
	event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
	const old = (keys) => keys.filter((key) => key.startsWith("kasbbook-") && key !== CACHE);
	event.waitUntil(
		caches.keys()
			.then((keys) => Promise.all(old(keys).map((key) => caches.delete(key))))
			.then(() => self.clients.claim()),
	);
});
self.addEventListener("fetch", (event) => {
	const { request } = event;
	const { origin, pathname } = new URL(request.url);
	if (request.method !== "GET" || request.mode === "navigate") return;
	if (origin !== location.origin || !FILES.includes(pathname)) return;
	event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
});
