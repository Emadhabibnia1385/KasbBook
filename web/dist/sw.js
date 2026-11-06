const CACHE = "kasbbook-da36a79978";
const FILES = ["/assets/BookRequired-2ZRo0qmr.js","/assets/BottomSheet-DzdXlIH3.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-CojkcdOR.js","/assets/ConfirmDialog-CWNT4iEY.js","/assets/CurrencyPicker-DbUVPLn1.js","/assets/DataTable-DkcdnLlv.js","/assets/DateTimeField-nLojzgkI.js","/assets/DayField-C0kBhp_F.js","/assets/DeveloperFooter-BPM8eN-u.js","/assets/ErrorState-Ctrz55be.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-5oy1CVnc.js","/assets/InstallButton-DtVQnutd.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-AYqUJNLb.js","/assets/Notice-BR7hGAeP.js","/assets/PageHeader-DPua-d_A.js","/assets/PayrollPage-oY_v2CkG.js","/assets/ProfileForm-BvTPVF8S.js","/assets/SearchBox-B1NiTlR7.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-CpOqnBeD.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-C2E_swme.js","/assets/SwitchField-B6FP8bvj.js","/assets/TextField-CkThw54R.js","/assets/_app-CaGQK5ne.js","/assets/_app.account-hweV-vSM.js","/assets/_app.books-BsdN4K-a.js","/assets/_app.index-9Mvw2X2c.js","/assets/_app.more-CcDrLPKe.js","/assets/_app.planning-DPVcKkR9.js","/assets/_app.recurring-CbG8jvKm.js","/assets/_app.reports-9OYWGk0U.js","/assets/_app.team-DsofrTVF.js","/assets/_app.team.funds-TOwAA6Gc.js","/assets/_app.team.index-DclMHYVq.js","/assets/_app.team.periods._periodId-BP9Fdznm.js","/assets/_app.team.periods.index-B3CsIuIF.js","/assets/_app.team.shares-BikrfPLN.js","/assets/_app.transactions-C8sznrBR.js","/assets/_app.wallet-olAhxv0S.js","/assets/accent-DyImK8HR.js","/assets/auth-1xWXIlCG.js","/assets/books-jFq1K5D1.js","/assets/calendar-CSrm6Fth.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-BwA9xFdN.js","/assets/format-yhtkESqM.js","/assets/icons-CTIHdB1I.js","/assets/index-B9ziZBXG.js","/assets/index-Bao_ijs3.css","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-ComoSgpH.js","/assets/market-rRdt-pk7.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-CiT_01Aj.js","/assets/overlays-B6_0Fie8.js","/assets/queryDefaults-DK_tKDM3.js","/assets/rules-Co37Xx-v.js","/assets/schemas-DflquWjh.js","/assets/shared-DXthtLTW.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-BrbXfmmc.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-VeMWLhsz.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-C4kjfSr1.js","/assets/useCatalog-CL2GCBPZ.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-CtW9h99S.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-DaKTpJ1z.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
