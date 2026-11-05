const CACHE = "kasbbook-54a4bb31c5";
const FILES = ["/assets/BottomSheet-CPOTvJbS.js","/assets/Charts-D9UrECKf.js","/assets/ChoiceFields-l6UTf9Uz.js","/assets/Collapsible-D_5tqPUy.js","/assets/ConfirmDialog-7iTngKmN.js","/assets/CurrencyPicker-CPBtJOVo.js","/assets/DataTable-8mKU1om7.js","/assets/DateTimeField-CZqabbu-.js","/assets/DayField-BxwkBbdg.js","/assets/DragAndDrop-cT4ymukK.js","/assets/ErrorState-Dz9WpkKw.js","/assets/FilterChips-DKCsB0uO.js","/assets/FocusScope-B96WV8wy.js","/assets/InstallButton-C5HfhlZa.js","/assets/KeyValueList-lr2rfvUu.js","/assets/Link-lYQXONkh.js","/assets/Modal-H1ZP9wgX.js","/assets/Notice-Cfyt-c-0.js","/assets/PageHeader-CvQXAM9D.js","/assets/PayrollPage-DTVz6r6D.js","/assets/SearchBox-BuZbIInR.js","/assets/SectionCard-zZkMkjCF.js","/assets/SelectField-Oa_JApkM.js","/assets/SelectionIndicator-DOT6l-u8.js","/assets/StatusChip-B4s-oZP-.js","/assets/SwitchField-DePs3hGI.js","/assets/TextField-Mq5GgApW.js","/assets/ThemeToggle-Dq6rJGN9.js","/assets/_app-AaLAK1rV.js","/assets/_app.account-PZU55OCs.js","/assets/_app.books-B_79LKWE.js","/assets/_app.index-DwwkAyHR.js","/assets/_app.more-Dsn3LGLg.js","/assets/_app.planning-BgijDslb.js","/assets/_app.recurring-ylsQyDnv.js","/assets/_app.reports-CNtcZjgz.js","/assets/_app.team-ClhzQytg.js","/assets/_app.team.funds-CK6MzDO8.js","/assets/_app.team.index-Zi9jx8oq.js","/assets/_app.team.periods._periodId-ZwMtrTcU.js","/assets/_app.team.periods.index-5bkjDgqW.js","/assets/_app.team.shares-DbmBUtZ3.js","/assets/_app.transactions-BCI928fe.js","/assets/_app.wallet-DVheHVvR.js","/assets/accent-BHxkCfca.js","/assets/calendar-C35FAti_.js","/assets/format-P-qd1Sc3.js","/assets/icons-DfaKGzLC.js","/assets/index-BeB4k9lb.js","/assets/index-BqRntWD_.css","/assets/lazyRouteComponent-DswuQ65A.js","/assets/link-C4nbkpf9.js","/assets/login-l6w3lANK.js","/assets/matchContext-Dwhe8nlG.js","/assets/mutations-BruLIq0J.js","/assets/queryDefaults-OHv_MmCL.js","/assets/schemas-DwQHBaTJ.js","/assets/shared-DdRKXLq9.js","/assets/signOut-B6PObmuB.js","/assets/status-C7SjyUYO.js","/assets/strings-DnSs5-Dl.js","/assets/surface-4vHQxcVu.js","/assets/table.styles-D47bsTSA.js","/assets/tables-DWSjfz6S.js","/assets/transport-B8lmXR-A.js","/assets/ui-BFIrJrrh.js","/assets/useActiveBook-CQVam54U.js","/assets/useCatalog-BRR9qUSF.js","/assets/useHasTabbableChild-DDAupdHy.js","/assets/useHover-ByWw_PNp.js","/assets/useIsNarrow-DhxaCmCc.js","/assets/useMatch-CtkG3y17.js","/assets/useNavigate-BisIcMb7.js","/assets/useRates-4FYscjDP.js","/assets/useRouter-QqB_lvx3.js","/assets/useSelector-CwBE5_mI.js","/assets/useSlot-D9iZEekL.js","/assets/useSpinButton-D76qCZcD.js","/assets/useTextField-C56Lvxri.js","/assets/useToggleState-CFboESHi.js","/assets/useUpdateEffect-B5HkMNJv.js","/assets/with-selector-Dl1-WAIz.js"];
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
