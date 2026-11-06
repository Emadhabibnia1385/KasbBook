const CACHE = "kasbbook-ebde83bb0e";
const FILES = ["/assets/BottomSheet-CTlPZwBo.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-Ci2bsZ0U.js","/assets/ConfirmDialog-kZsV0iko.js","/assets/CurrencyPicker-BMZZl-WD.js","/assets/DataTable-BBm4h4Or.js","/assets/DateTimeField-Dbjwk7dx.js","/assets/DayField-CkleNezI.js","/assets/ErrorState-DxgX0BjN.js","/assets/FilterChips-BMx6oDgh.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-B1zvjTBp.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Modal-DC7P3oDl.js","/assets/Notice-DcnMA3kl.js","/assets/PageHeader-C6ahoJ_J.js","/assets/PayrollPage-ocW9SSei.js","/assets/SearchBox-DrpPAYTR.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-Dy6aj7wS.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-Bqa-1fuk.js","/assets/SwitchField-CPcKYUyi.js","/assets/TextField-BBFZRi0-.js","/assets/_app-CoHUdUkA.js","/assets/_app.account-2dgDbsbt.js","/assets/_app.books-BI_dAYt6.js","/assets/_app.index-CixKdlw0.js","/assets/_app.more-C6Shqecw.js","/assets/_app.planning-jUNdAOUG.js","/assets/_app.recurring-OFQT4Fpw.js","/assets/_app.reports-DjB78Pyp.js","/assets/_app.team-DFfO4RRe.js","/assets/_app.team.funds-BnKZadw4.js","/assets/_app.team.index-C680AFOh.js","/assets/_app.team.periods._periodId-DwkbutS-.js","/assets/_app.team.periods.index-C9PFFOFt.js","/assets/_app.team.shares-DHwFE8Ho.js","/assets/_app.transactions-9rJWWS5m.js","/assets/_app.wallet-WLLgBXMn.js","/assets/accent-BAY4al-W.js","/assets/calendar-C35FAti_.js","/assets/clock-CcMCmObk.js","/assets/decimal-6YOdUFZ2.js","/assets/format-P-qd1Sc3.js","/assets/headerPrefs-DSiBFjpe.js","/assets/icons-JcburOYw.js","/assets/index-CPknooZu.js","/assets/index-JJOJE6qi.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-BCGN4Gix.js","/assets/market-BfOuBAgO.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-C0mz0k4J.js","/assets/queryDefaults-C4R5YeQM.js","/assets/schemas-BtS3UgpE.js","/assets/shared-D4DtnS9W.js","/assets/signOut-N3PBcaJo.js","/assets/status-C7SjyUYO.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-ZwFeAlG1.js","/assets/tickerPrefs-pfD3nmBd.js","/assets/transport-dis_3XmR.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-C7S95DeV.js","/assets/useCatalog-BpAXGDNf.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useQuotes-BSWoqrid.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-Xahvwqnc.js","/assets/useTextField-JWxv9B7u.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
