const CACHE = "kasbbook-03042aecf4";
const FILES = ["/assets/BottomSheet-Z_FxUcdT.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-BoB1QO04.js","/assets/ConfirmDialog-BejipaWb.js","/assets/CurrencyPicker-BvkNlTZs.js","/assets/DataTable-DUfiSzKx.js","/assets/DateTimeField-a-dhfNCi.js","/assets/DayField-QRU0GdQq.js","/assets/ErrorState-DjeFNiA1.js","/assets/FilterChips-DMfKF43o.js","/assets/FocusScope-B96WV8wy.js","/assets/GithubStar-Ckf8nGE4.js","/assets/InstallButton-Syc1g9VM.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-BNFGRBce.js","/assets/Notice-JiZpsSgf.js","/assets/PageHeader-Dh_9UQsO.js","/assets/PayrollPage-D_-TQsz6.js","/assets/SearchBox-CDn5DOzN.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-CfjvNx5t.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-VXrz1Zpe.js","/assets/SwitchField-DJN_OKOz.js","/assets/TextField-0xI5rZoq.js","/assets/_app-jORJ_l_Q.js","/assets/_app.account-jbPUdVI4.js","/assets/_app.books-C_IyKR3K.js","/assets/_app.index-DjyIX-cy.js","/assets/_app.more-CzEVLOkm.js","/assets/_app.planning-P9asX88O.js","/assets/_app.recurring-UNLeKYix.js","/assets/_app.reports-DwTHEOWW.js","/assets/_app.team-BCyDz_TR.js","/assets/_app.team.funds-BYrfPf65.js","/assets/_app.team.index-DiIRl_Jf.js","/assets/_app.team.periods._periodId-BLumvGtF.js","/assets/_app.team.periods.index-qwFyzSDz.js","/assets/_app.team.shares-BabTUOJh.js","/assets/_app.transactions-BpgCLEeQ.js","/assets/_app.wallet-Cr78iUOg.js","/assets/accent-ClU1oxcM.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DxgqgQ3X.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-Bu3Ik6si.js","/assets/icons-JcburOYw.js","/assets/index-2zx63RyV.css","/assets/index-D0pK5OLB.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-Dg692sr2.js","/assets/market-D2Yll5iq.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-RACPLhH8.js","/assets/queryDefaults-AAhyYZZH.js","/assets/schemas-DCW0tca1.js","/assets/shared-CfAqG-oG.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-DP1puUNo.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-DeBQ-op0.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-CO2cbcuX.js","/assets/useCatalog-08bZD5oJ.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-CV03r1je.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-EvjSLMwD.js","/assets/useTextField-Ce8eETZp.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
