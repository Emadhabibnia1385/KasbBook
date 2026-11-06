const CACHE = "kasbbook-7d3a8127ad";
const FILES = ["/assets/BookRequired-7sBC61Fh.js","/assets/BottomSheet-DiLb3fzD.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-HFpRahu_.js","/assets/ConfirmDialog-D7OA_ndK.js","/assets/CurrencyPicker-C9bmw0vH.js","/assets/DataTable-D2YHcoeT.js","/assets/DateTimeField-DPXrc9Ho.js","/assets/DayField-abRCQHOI.js","/assets/DeveloperFooter-CK7SEaCB.js","/assets/ErrorState-Bliq0-qq.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-Clpt0K0o.js","/assets/InstallButton-2KfqH30m.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-Cb0HR6hF.js","/assets/Notice-F6vKahKD.js","/assets/PageHeader-CHGrD5jR.js","/assets/PayrollPage-JKT8k_kO.js","/assets/ProfileForm-Dh6uFjf3.js","/assets/SearchBox-7k-0AoQ9.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-DkMFsYAb.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-BiDeJJSq.js","/assets/SwitchField-ClrbfHtp.js","/assets/TextField-0gGlAzkx.js","/assets/_app-BXpXbAYT.js","/assets/_app.account-vArqPpd2.js","/assets/_app.books-hIQzZXXW.js","/assets/_app.index-5q7wOOez.js","/assets/_app.more-C85xQCda.js","/assets/_app.planning-iUMbuCF3.js","/assets/_app.recurring-D2g_WaUM.js","/assets/_app.reports-ZJTt1MUR.js","/assets/_app.team-DkKveKAr.js","/assets/_app.team.funds-BihHXNVp.js","/assets/_app.team.index-35OfyoGd.js","/assets/_app.team.periods._periodId-wXNMdNOy.js","/assets/_app.team.periods.index-DTebAUyg.js","/assets/_app.team.shares-D0nTMxaX.js","/assets/_app.transactions-C2VVcpsU.js","/assets/_app.wallet-DyinkjpZ.js","/assets/accent-Bn6zDURw.js","/assets/auth-C7QnBQO5.js","/assets/books-CR6ofVaG.js","/assets/calendar-CSrm6Fth.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DaDmtoI_.js","/assets/format-yhtkESqM.js","/assets/icons-CTIHdB1I.js","/assets/index-Bao_ijs3.css","/assets/index-ubgaPzWF.js","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-MpMfoiJI.js","/assets/market-BcSNjLYr.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-RfooTfaH.js","/assets/overlays-D9d4sk8w.js","/assets/queryDefaults-hDUf0rB6.js","/assets/rules-BJcru9Y0.js","/assets/schemas-MsVmvpdY.js","/assets/shared-AQYChbdk.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-5olk62xk.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-GGS3T8-n.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-agj_PUpS.js","/assets/useCatalog-BHtfDwAf.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-BYmiBvP3.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-Drn-rtnI.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
