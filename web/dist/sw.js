const CACHE = "kasbbook-3fb082b20e";
const FILES = ["/assets/BookRequired-Da2jCNn_.js","/assets/BottomSheet-BWR7sE3W.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-39McmiHz.js","/assets/ConfirmDialog-BhRF3bAQ.js","/assets/CurrencyPicker-DQnrN163.js","/assets/DataTable-CxhoUMRY.js","/assets/DateTimeField-DJC5b3mr.js","/assets/DayField-s8lv9kv8.js","/assets/ErrorState-DPmcuvDK.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubLink-Du0qOxK-.js","/assets/InstallButton-BmWCnPkj.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-BmMGTp2h.js","/assets/Modal-eWWLoJ6h.js","/assets/Notice-DRZeOZSc.js","/assets/PageHeader-Ba4LmUoL.js","/assets/PayrollPage-BCOu9DZP.js","/assets/SearchBox-bAzJN8aG.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-D1stIbJq.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-BgcByD3N.js","/assets/SwitchField-Dy2PiZb5.js","/assets/TextField-CRDDPPDo.js","/assets/_app-27Eb8DVA.js","/assets/_app.account-CwahilV7.js","/assets/_app.books-B7fxzvXn.js","/assets/_app.index-CyVcgkMb.js","/assets/_app.more-CqYEdQdO.js","/assets/_app.planning-BqIB2NwM.js","/assets/_app.recurring-dgwuq2Au.js","/assets/_app.reports-BTi3MgJq.js","/assets/_app.team-DhUWA_-7.js","/assets/_app.team.funds-BmcYjhVS.js","/assets/_app.team.index-w8RBMbTV.js","/assets/_app.team.periods._periodId-WxTRKfxg.js","/assets/_app.team.periods.index-DWlRaxNr.js","/assets/_app.team.shares-CZ4sMNOi.js","/assets/_app.transactions-DFyy_6M7.js","/assets/_app.wallet-C2FFZ-ba.js","/assets/accent-U8zmoVdm.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-CiHoMDti.js","/assets/format-P-qd1Sc3.js","/assets/icons-BFi6_TSm.js","/assets/index-COc6x0QH.css","/assets/index-DwTtIpqT.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-BujirYTE.js","/assets/market-D52_KKRr.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-DWT0b_fo.js","/assets/queryDefaults-BBH3IujK.js","/assets/quickPrefs-CKd7lvWo.js","/assets/rules-DMSoTp_H.js","/assets/schemas-iKM0eS4p.js","/assets/shared-B4m80UC7.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-ejey_Q02.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transactions-C0_hjY7c.js","/assets/transport-D1Gp970p.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-BQLr9HEq.js","/assets/useCatalog-DuQHV6bz.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-0oU4Zr_c.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-D9_JsCWH.js","/assets/useTextField-YZCD74Af.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
