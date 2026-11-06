const CACHE = "kasbbook-fe8d3e4112";
const FILES = ["/assets/BookRequired-BAlljNgS.js","/assets/BottomSheet-DK3A05RW.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-kH_4Glrb.js","/assets/ConfirmDialog-viiskBdM.js","/assets/CurrencyPicker-B_bt4Sh6.js","/assets/DataTable-YyS1wQ2_.js","/assets/DateTimeField-cfQihvD5.js","/assets/DayField-7AGzVNiS.js","/assets/ErrorState-BdXyxV84.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubLink-EJsgVjeL.js","/assets/InstallButton-D8gL8Mj7.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-BmMGTp2h.js","/assets/Modal--uXkDmOk.js","/assets/Notice-r9qtQV9r.js","/assets/PageHeader-CMqJlOZP.js","/assets/PayrollPage-ChPmJBKI.js","/assets/SearchBox-DeewRW9o.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-CAD_mtjp.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-B1ddGxUJ.js","/assets/SwitchField-CEM7WjiO.js","/assets/TextField-BAyODpCK.js","/assets/_app-CIV2BGCW.js","/assets/_app.account-Di072Zad.js","/assets/_app.books-BCoaHJcB.js","/assets/_app.index-DoA1ZwT0.js","/assets/_app.more-D_Q4M2_u.js","/assets/_app.planning-BHB1DnFI.js","/assets/_app.recurring-Dp_Ufy1b.js","/assets/_app.reports-BLirX-HG.js","/assets/_app.team-DBtHaFnc.js","/assets/_app.team.funds-BX1eLwkh.js","/assets/_app.team.index-otbXrwlx.js","/assets/_app.team.periods._periodId-Ci3mJBrI.js","/assets/_app.team.periods.index-CsRmQM92.js","/assets/_app.team.shares-DnR-W2WS.js","/assets/_app.transactions-DRCC2x3a.js","/assets/_app.wallet-C6Lzxags.js","/assets/accent-CD9V5b6W.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DpkPJEcX.js","/assets/format-P-qd1Sc3.js","/assets/icons-BFi6_TSm.js","/assets/index-BBXFnclq.js","/assets/index-Dwwgdp8g.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-fGjWc60t.js","/assets/market-O56vhQX_.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-BMypHlPi.js","/assets/queryDefaults-BeN_A7Wx.js","/assets/quickPrefs-vJ1rcVji.js","/assets/rules-Bg9m34Ub.js","/assets/schemas-D2nT47RR.js","/assets/shared-DZQP1Q8T.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-jnbkt1pW.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transactions-DT2cr4Zx.js","/assets/transport-C3mpU2d5.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-DNhCj70H.js","/assets/useCatalog-CgR0liZ7.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-K7kqPJWZ.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-BDSejLRd.js","/assets/useTextField-haEYYIkf.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
