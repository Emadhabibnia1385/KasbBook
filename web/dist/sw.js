const CACHE = "kasbbook-71a555a5e5";
const FILES = ["/assets/BookRequired-Bbk93Xp4.js","/assets/BottomSheet-P1iveq6r.js","/assets/Charts-D4zO68xW.js","/assets/ChoiceFields-Ow_1FD8p.js","/assets/ConfirmDialog-BVQVejzI.js","/assets/CurrencyPicker-Dujhg4bu.js","/assets/DataTable-CnTBYx6K.js","/assets/DateTimeField-Ce5M4s4b.js","/assets/DayField-DBn0JAnv.js","/assets/DeveloperFooter-DSxmd0DB.js","/assets/ErrorState-BdW7kpPO.js","/assets/FilterChips-C26w1Sdq.js","/assets/GithubLink-PGYiNmMf.js","/assets/InstallButton-BRkMnA5D.js","/assets/KeyValueList-CS0VSITk.js","/assets/Link-BwrYPIid.js","/assets/Modal-tF8DK5We.js","/assets/Notice-DKWHObIM.js","/assets/PageHeader-CfosYZwI.js","/assets/PayrollPage-CY2tf4nL.js","/assets/ProfileForm-B-2k3qCk.js","/assets/SearchBox-b7mcgUJx.js","/assets/SectionCard-0Dx-imW-.js","/assets/SelectField-BZtId2me.js","/assets/SelectionIndicator-Dc0SBySl.js","/assets/StatusChip-CJxSJWKe.js","/assets/SwitchField-vusP8QEi.js","/assets/TextField-BQqujH2z.js","/assets/_app-DS7PJvJW.js","/assets/_app.account-5uBg_kwn.js","/assets/_app.books-CwHb4hrV.js","/assets/_app.index-CqFrT2Mt.js","/assets/_app.more-CAyYL0dO.js","/assets/_app.planning-DWkLAKPT.js","/assets/_app.recurring-DjFpyNXf.js","/assets/_app.reports-DcGl0QlW.js","/assets/_app.team-DSgzFcKg.js","/assets/_app.team.funds-3_9v09gA.js","/assets/_app.team.index-BaM6EiTj.js","/assets/_app.team.periods._periodId-_ONrhG0c.js","/assets/_app.team.periods.index-B2wcmXWC.js","/assets/_app.team.shares-DViX3mU-.js","/assets/_app.transactions-DyTDXkpW.js","/assets/_app.wallet-BTRlQXhI.js","/assets/accent-akBij7uV.js","/assets/books-BlCsfswg.js","/assets/calendar-C35FAti_.js","/assets/clock-D8LlN1Fp.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DZdlnDsX.js","/assets/format-bak8e2q-.js","/assets/icons-CTIHdB1I.js","/assets/index-BaSeiWlE.js","/assets/index-MJFncYac.css","/assets/lazyRouteComponent-CjRywOmq.js","/assets/link-M86a8oEv.js","/assets/login-Cwg_IXjA.js","/assets/market-CL6UyBVw.js","/assets/matchContext-DmX0tGDU.js","/assets/mutations-DuLbwE9-.js","/assets/overlays-BfY6-Qcd.js","/assets/queryDefaults-CqnJ_xTs.js","/assets/rules-CV6JYZEc.js","/assets/schemas-Cm2rRPLk.js","/assets/shared-BjWpuR-4.js","/assets/status-C7SjyUYO.js","/assets/strings-Ctuc9eFV.js","/assets/surface-itiypn0z.js","/assets/table.styles-DWhb3RN8.js","/assets/tables-DYKeEZMU.js","/assets/tickerPrefs-BLEkZLZo.js","/assets/transactions-BacfjNa8.js","/assets/ui-Bdc6sSvG.js","/assets/useActiveBook-BEzaZUwn.js","/assets/useCatalog-D-VKWEFp.js","/assets/useHasTabbableChild-BQ_FsyYZ.js","/assets/useHover-BFKuvMv4.js","/assets/useIsNarrow-DfZ3NEa3.js","/assets/useMatch-C3uy1ZdQ.js","/assets/useNavigate-BiRAT0gK.js","/assets/useQuotes-BNMCkpM9.js","/assets/useRouter-DDQhmSJN.js","/assets/useSelector-LA0H9FxF.js","/assets/useSlot-BDaqjXzG.js","/assets/useSpinButton-DVTMtnwy.js","/assets/useToggleState-DbtVrnZn.js","/assets/useUpdateEffect-CHWv7OKs.js","/assets/with-selector-CLcdDC5i.js"];
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
