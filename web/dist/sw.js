const CACHE = "kasbbook-ae666d3d7b";
const FILES = ["/assets/BookRequired-CLAy6dRX.js","/assets/BottomSheet-XF9yzB4n.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-nX0ccU7G.js","/assets/ConfirmDialog-B8pk_88B.js","/assets/CurrencyPicker-BFd7zWWW.js","/assets/DataTable-BUa5Fu3q.js","/assets/DateTimeField-DoU8xEpk.js","/assets/DayField-bBaP2BQi.js","/assets/ErrorState-CqyoeQvT.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubLink-VYFhwYzX.js","/assets/InstallButton-DVMYNnrO.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-BmMGTp2h.js","/assets/Modal-AVQb5a-X.js","/assets/Notice-BmBvq2pz.js","/assets/PageHeader-DSa0QqR2.js","/assets/PayrollPage-DAHXjf8S.js","/assets/SearchBox-D79ufVGi.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-BCncFrRP.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-C9y6EUpi.js","/assets/SwitchField-CJP9zLxA.js","/assets/TextField-DLoe64ih.js","/assets/_app-J6tiy6nB.js","/assets/_app.account-DKzB3BBA.js","/assets/_app.books-BjdoLnkA.js","/assets/_app.index-B_w1Yo1W.js","/assets/_app.more-C01h9L1O.js","/assets/_app.planning-BfQsgs5K.js","/assets/_app.recurring-BnYBm7s0.js","/assets/_app.reports-CdHIX4nJ.js","/assets/_app.team-aKi2FS6P.js","/assets/_app.team.funds-Bl9ovrtm.js","/assets/_app.team.index-D3LRa5JH.js","/assets/_app.team.periods._periodId-Cw_bBzZz.js","/assets/_app.team.periods.index-DhCkHSi6.js","/assets/_app.team.shares-Dffl1p8V.js","/assets/_app.transactions-B5hqoO0U.js","/assets/_app.wallet-CFdmYkZj.js","/assets/accent-BX112FKn.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DMfAzUiV.js","/assets/format-P-qd1Sc3.js","/assets/icons-BFi6_TSm.js","/assets/index-02IUMEWl.css","/assets/index-D0CeETGh.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-FnegWydN.js","/assets/market-mG_o3hRl.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-CAZl_Xpq.js","/assets/queryDefaults-43t4_4wU.js","/assets/quickPrefs-DAdW42Hn.js","/assets/rules-wbmB4Mes.js","/assets/schemas-QZraL22H.js","/assets/shared-pQMJEwPk.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-5Kx3lrcU.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transactions-B3Jc42eq.js","/assets/transport-tHWyfybK.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-tq4ILI-B.js","/assets/useCatalog-B7wjzgA8.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-D0xfSTs_.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-GxFlSCst.js","/assets/useTextField-g2M4NCOM.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
