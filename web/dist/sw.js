const CACHE = "kasbbook-c90dbf4248";
const FILES = ["/assets/BottomSheet-C9PX0Cwl.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-BVR0YQZW.js","/assets/ConfirmDialog-t_K_hLbz.js","/assets/CurrencyPicker-7gNaCbmC.js","/assets/DataTable-D_rN1gSx.js","/assets/DateTimeField-hV2hjoId.js","/assets/DayField-DQaRWK5y.js","/assets/ErrorState-DgPvzffq.js","/assets/FilterChips-BwcyZRv2.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubStar-KyuGSNpp.js","/assets/InstallButton-DDw4qeFV.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-CmXZTw3T.js","/assets/Notice-DOG3YXhS.js","/assets/PageHeader-Boq-1P5R.js","/assets/PayrollPage-aDBHkJzw.js","/assets/SearchBox-CoqMSHR4.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-9zd7I3gL.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-CUFbLnmg.js","/assets/SwitchField-BNKX_V0y.js","/assets/TextField-H0r65RIk.js","/assets/_app-CxG8fER-.js","/assets/_app.account-D-F5stQ9.js","/assets/_app.books-DTmrmpDe.js","/assets/_app.index-BQxR-tuG.js","/assets/_app.more-rHMi8Msu.js","/assets/_app.planning-B0XOzjne.js","/assets/_app.recurring-Bv88Kwoq.js","/assets/_app.reports-C15EhKww.js","/assets/_app.team-DX1ZAo4m.js","/assets/_app.team.funds-CJeT1XK7.js","/assets/_app.team.index-DxjrU8DA.js","/assets/_app.team.periods._periodId-CobwSv9N.js","/assets/_app.team.periods.index-Bwfn1d56.js","/assets/_app.team.shares-DMTiMggb.js","/assets/_app.transactions-yDhUaYI3.js","/assets/_app.wallet-Bzw8E0uG.js","/assets/accent-C0XAZsdT.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-B91NlI9J.js","/assets/icons-JcburOYw.js","/assets/index-2zx63RyV.css","/assets/index-C-8XFT_3.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-Bsr4nDoO.js","/assets/market-DpVWVdyC.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-iLa0nI6b.js","/assets/queryDefaults-DFUxwa2w.js","/assets/schemas-cZ43WtFQ.js","/assets/shared-DlMR7TZG.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-Whs8atn6.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-DKv1-cVh.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-DY-6k9ul.js","/assets/useCatalog-DXik7IcA.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-gEE7FtN-.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-BZvBmT1W.js","/assets/useTextField-BEyCi1UR.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
