const CACHE = "kasbbook-df3d38e363";
const FILES = ["/assets/BottomSheet-Ctpmsy41.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-B7JvtZvT.js","/assets/ConfirmDialog-JzTRkCvg.js","/assets/CurrencyPicker-CnGlsUts.js","/assets/DataTable-C7u_VCR-.js","/assets/DateTimeField-CFzvZ3YQ.js","/assets/DayField-Eb_4VANM.js","/assets/ErrorState-hXXwU2kj.js","/assets/FilterChips-BKmXFZ3B.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-CqLiXVle.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-CyoZxzX3.js","/assets/Notice-CsvSroHA.js","/assets/PageHeader-B6YKvXH9.js","/assets/PayrollPage-DdAgljJl.js","/assets/SearchBox-VqWWzOah.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField--nvngyMX.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-BI6JO72S.js","/assets/SwitchField-CCr5TTgi.js","/assets/TextField-DzFt9PjC.js","/assets/_app-pUe1BH_G.js","/assets/_app.account-DI48Wa7s.js","/assets/_app.books-CVZjVGza.js","/assets/_app.index-DlnpFQHh.js","/assets/_app.more-CESNql_C.js","/assets/_app.planning-CjVGUYS_.js","/assets/_app.recurring-BYqJjHad.js","/assets/_app.reports-DgouzHpN.js","/assets/_app.team-B0GhLt6u.js","/assets/_app.team.funds-qQHi4LY2.js","/assets/_app.team.index-q-rrRvHs.js","/assets/_app.team.periods._periodId-BRDYkpiL.js","/assets/_app.team.periods.index-QClmVnLI.js","/assets/_app.team.shares-DsBpHljs.js","/assets/_app.transactions-DknBIFOW.js","/assets/_app.wallet-BijA_cev.js","/assets/accent-CVyHyWCS.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-DvaitBUk.js","/assets/icons-JcburOYw.js","/assets/index-CU_ugHU3.css","/assets/index-DwLvhA5L.js","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-w6gMJg5j.js","/assets/market-DbFkUGnR.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-BXrwe25E.js","/assets/queryDefaults-J-yfeeJZ.js","/assets/schemas-DDwxmMGV.js","/assets/shared--vcVxOjK.js","/assets/signOut-B7t864Gr.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-D5nNMlq5.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-1QyFNM34.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-BhX59mQB.js","/assets/useCatalog-CsBk8G46.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-Bo5Rv02I.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-iTK8bvcD.js","/assets/useTextField-CPLGj2Mz.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
