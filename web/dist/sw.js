const CACHE = "kasbbook-b419c34980";
const FILES = ["/assets/BottomSheet-CVG8umVw.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-C4esME47.js","/assets/Collapsible-yqogPykN.js","/assets/ConfirmDialog-8c3WMK3w.js","/assets/CurrencyPicker-d6JizmM-.js","/assets/DataTable-DaAfDF-_.js","/assets/DateTimeField-mRdwT_Ff.js","/assets/DayField-CB-8TndA.js","/assets/DragAndDrop-BS6hX7TY.js","/assets/ErrorState-Cxowq86L.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-CxJJn63Z.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-lYQXONkh.js","/assets/Modal-Cp0U2J6G.js","/assets/Notice-B3KdylnX.js","/assets/PageHeader-D5ig52m-.js","/assets/PayrollPage-D92D3cU0.js","/assets/SearchBox-Dt2UjGSa.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-Q2K7nI0G.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-BgBawF2_.js","/assets/SwitchField-CF3wr3N8.js","/assets/TextField-jymrNXNC.js","/assets/ThemeToggle-CX9vdpPN.js","/assets/_app-CQe6hDNC.js","/assets/_app.account-CQoKpFMb.js","/assets/_app.books-Di8Bwf1h.js","/assets/_app.index-ADEBrVsF.js","/assets/_app.more-DCd_8fyK.js","/assets/_app.planning-DG_nGznY.js","/assets/_app.recurring-meRy9QAR.js","/assets/_app.reports-CsAueKZe.js","/assets/_app.team-CQ3MbPbe.js","/assets/_app.team.funds-B4lopU37.js","/assets/_app.team.index-DaYdu-j1.js","/assets/_app.team.periods._periodId-CPBsMY_9.js","/assets/_app.team.periods.index-LD2cNha6.js","/assets/_app.team.shares-D4GogoxQ.js","/assets/_app.transactions-CIw-SSgw.js","/assets/_app.wallet-CGFTiGAg.js","/assets/accent-9ROhkU72.js","/assets/calendar-C35FAti_.js","/assets/format-P-qd1Sc3.js","/assets/icons-DfaKGzLC.js","/assets/index-1_Snofks.js","/assets/index-BuRoho-R.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-DYcYwRVK.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-okeWZ94U.js","/assets/queryDefaults-QY5UrxJe.js","/assets/schemas-BUhciPSg.js","/assets/shared-DIdwHDCJ.js","/assets/signOut-D5rfM3zy.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-DBPWKWN5.js","/assets/transport-DedLr6KM.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-fv4KXXSn.js","/assets/useCatalog-C2s06-6E.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useRates-bHhLxkrR.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-BqqFULZ-.js","/assets/useTextField-sCTyjLPZ.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
