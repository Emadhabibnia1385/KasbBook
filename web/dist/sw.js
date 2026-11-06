const CACHE = "kasbbook-28c5cfc50c";
const FILES = ["/assets/BookRequired-B1TFGer2.js","/assets/BottomSheet-vBHtEzXJ.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-D8xdv0sv.js","/assets/ConfirmDialog-C9HX3j0Y.js","/assets/CurrencyPicker-EIF9KgoF.js","/assets/DataTable-CnDFdtsQ.js","/assets/DateTimeField-QwcnwIP3.js","/assets/DayField-l-n1jQFt.js","/assets/DeveloperFooter-CxuofiLp.js","/assets/ErrorState-xT9d2Rq6.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-8QZTKW6h.js","/assets/InstallButton-4IjNhcXn.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-oR4Oh5fR.js","/assets/Notice-DsYKDEjj.js","/assets/PageHeader-CBqmHpnu.js","/assets/PayrollPage-CGVS3tyG.js","/assets/ProfileForm-C0Z3bRgq.js","/assets/SearchBox-BwiK3_pj.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-Df38VqHF.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-DIoKHIR3.js","/assets/SwitchField-pVGeCj-y.js","/assets/TextField-DyXJY-e5.js","/assets/_app-FT6UarYI.js","/assets/_app.account-DkmIOlO5.js","/assets/_app.books-BjEEYOFI.js","/assets/_app.index-Hy8i5rMq.js","/assets/_app.more-D03Pt1tH.js","/assets/_app.planning-DMTjCZIe.js","/assets/_app.recurring-_9YLXOhh.js","/assets/_app.reports-Drjl9bDs.js","/assets/_app.team-BkedFugH.js","/assets/_app.team.funds-BWjt65Gs.js","/assets/_app.team.index-hD61ONl-.js","/assets/_app.team.periods._periodId-B831yy00.js","/assets/_app.team.periods.index-BVHRfH4C.js","/assets/_app.team.shares-9mA8GA0n.js","/assets/_app.transactions-BZhuqmkx.js","/assets/_app.wallet-DT6XHue7.js","/assets/accent-CcW3KXuK.js","/assets/books-Dy1p5274.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-D-BPPrpb.js","/assets/format-bak8e2q-.js","/assets/icons-CTIHdB1I.js","/assets/index-Bao_ijs3.css","/assets/index-CFMvsomt.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-ByB1CAY7.js","/assets/market-C0hmuQhq.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-B-2VzndL.js","/assets/overlays-Dc_38EHZ.js","/assets/queryDefaults-XS7t_7Aw.js","/assets/rules-CZueR4db.js","/assets/schemas-zPSkMghG.js","/assets/shared-W7E3SoCk.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-CfX4MvGa.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-DsFxxJ_0.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-DAGXKUIV.js","/assets/useCatalog-Bl9m4W4L.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-B8mfevN2.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-DJ_a0izr.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
