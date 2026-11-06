const CACHE = "kasbbook-d419780421";
const FILES = ["/assets/BottomSheet-CjxLA5BB.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-BwD80jqs.js","/assets/ConfirmDialog-B3lmr9-X.js","/assets/CurrencyPicker-DZNVnNNE.js","/assets/DataTable-CgPFwbSb.js","/assets/DateTimeField-OSuG70Ww.js","/assets/DayField-DjUItSQ7.js","/assets/ErrorState-D4dgs5FL.js","/assets/FilterChips-BAybUkvT.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubStar-Damy9m2C.js","/assets/InstallButton-BVyY_sRb.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-BntPPmJ2.js","/assets/Notice-DNsVAtpM.js","/assets/PageHeader-C-39xQbN.js","/assets/PayrollPage-DixE7nBk.js","/assets/SearchBox-SAOZ8D6W.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-pJIA85AR.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-C-kR974X.js","/assets/SwitchField-Bf_ZNM1Y.js","/assets/TextField-OGKrpSiW.js","/assets/_app-Bo8FQ_GW.js","/assets/_app.account-CNJwFJ_V.js","/assets/_app.books-BWUDThNV.js","/assets/_app.index-BfY4htLo.js","/assets/_app.more-CTBQpV7q.js","/assets/_app.planning-DIXH-Xqg.js","/assets/_app.recurring-C5olnBTh.js","/assets/_app.reports-DnUFsiXO.js","/assets/_app.team-DVuyZiSo.js","/assets/_app.team.funds-DftCoeDG.js","/assets/_app.team.index-DXjgUahT.js","/assets/_app.team.periods._periodId-DI4IIHEL.js","/assets/_app.team.periods.index-BMakZaAh.js","/assets/_app.team.shares-BVycbJ9D.js","/assets/_app.transactions-Ds7e9XFh.js","/assets/_app.wallet-Cfkn3RxZ.js","/assets/accent-DKMjO9WT.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-BHI1Oibb.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-Bac57LXS.js","/assets/icons-BK6FpNJ1.js","/assets/index-BT6NcjC9.js","/assets/index-D0gfnePA.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-DCcjjmUa.js","/assets/market-CYuiYXOI.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-CImi82YI.js","/assets/queryDefaults-wkGAGkCy.js","/assets/schemas-BCBQoCw1.js","/assets/shared-BctHK9yE.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-BmfdPuMf.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-McmkSNBP.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-B-tcfZS-.js","/assets/useCatalog-DLFzjPRb.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-CAN-5jnz.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-D2egkQYp.js","/assets/useTextField-CaeEA7pc.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
