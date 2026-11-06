const CACHE = "kasbbook-d82930b9c6";
const FILES = ["/assets/BottomSheet-TSZLUTgS.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-vCfSGdwt.js","/assets/ConfirmDialog-Bi5I5GWy.js","/assets/CurrencyPicker-CPehZxhJ.js","/assets/DataTable-D_XY3n0v.js","/assets/DateTimeField-DOMiNjU8.js","/assets/DayField-DbBMpbps.js","/assets/ErrorState-9L8qJYQK.js","/assets/FilterChips-Bvhuoaax.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-BqeyJdMJ.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-8NIYAuKi.js","/assets/Notice-hSOpU3L2.js","/assets/PageHeader-DHKi4Sdv.js","/assets/PayrollPage-UkjPoXh2.js","/assets/SearchBox-B5uLDp1x.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-DrlP-nYd.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-C7R3M56o.js","/assets/SwitchField-CXLw2tzW.js","/assets/TextField-DaRFn6Oc.js","/assets/_app-7NckWPlw.js","/assets/_app.account-BTuYNqBS.js","/assets/_app.books-CUZ7AY04.js","/assets/_app.index-Dxb6rwIR.js","/assets/_app.more-zvLAsmbP.js","/assets/_app.planning-eQyXLVyB.js","/assets/_app.recurring-BPhFSSop.js","/assets/_app.reports-DHlPpLBo.js","/assets/_app.team-CAG6sJCE.js","/assets/_app.team.funds-DaRtL0ru.js","/assets/_app.team.index-EzBEPr4C.js","/assets/_app.team.periods._periodId-C6tHg4Og.js","/assets/_app.team.periods.index-COFaWo5L.js","/assets/_app.team.shares-CDF6r3tb.js","/assets/_app.transactions-Cty2OTI1.js","/assets/_app.wallet-Cd9B31HD.js","/assets/accent-DeXyE73j.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-DfG5hC94.js","/assets/icons-JcburOYw.js","/assets/index-BHxseL_R.js","/assets/index-JJOJE6qi.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-uny8tulW.js","/assets/market-VZArAMmc.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-C6yF80bj.js","/assets/queryDefaults-DmR_jpmb.js","/assets/schemas-DQ9gowGq.js","/assets/shared-eSlMFBeG.js","/assets/signOut-BIkBtGuk.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-D5hDup3G.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-HuK1bjPV.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-C3XAwJbC.js","/assets/useCatalog-DjoJBQdV.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-DFpwLeMY.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-0MByQOIm.js","/assets/useTextField-DVLuQrPC.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
