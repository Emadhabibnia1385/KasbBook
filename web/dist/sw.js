const CACHE = "kasbbook-06a29abdb7";
const FILES = ["/assets/BottomSheet-Je6Ukwcd.js","/assets/Charts-_jzl05Me.js","/assets/ChoiceFields-Da4j1SVG.js","/assets/Collapsible-CfKTwCqJ.js","/assets/CollectionBuilder-DSvcDdfR.js","/assets/ConfirmDialog-DKODCJPy.js","/assets/CurrencyPicker-LYXeoFuN.js","/assets/DataTable-CBqLsFFo.js","/assets/DateTimeField-DLM7vOky.js","/assets/DayField-TmH32aEe.js","/assets/DragAndDrop-Bw27dUkk.js","/assets/ErrorState-BBwmvuIS.js","/assets/FilterChips-8X1nxdiH.js","/assets/FocusScope-BGa1Yhmr.js","/assets/InstallButton-DbW2eDd1.js","/assets/KeyValueList-BZomf-LS.js","/assets/Link-GVBmrGMs.js","/assets/Modal-CGe0MP_9.js","/assets/Notice-DHUOk7uf.js","/assets/PageHeader-C9Yi_qeU.js","/assets/PayrollPage-B7LQv9qD.js","/assets/SearchBox-BaMBppCN.js","/assets/SectionCard-4z_2u3vm.js","/assets/SelectField-D4Muy3P2.js","/assets/StatusChip-BRFPm95W.js","/assets/SwitchField-46Pdcizx.js","/assets/TextField-BZovrtFi.js","/assets/ThemeToggle-MCAXE9BL.js","/assets/_app-C2Kenlz3.js","/assets/_app.account-CfA2j1kD.js","/assets/_app.books-ucbDjvad.js","/assets/_app.index-BabFKdpK.js","/assets/_app.more-Cc4suK1a.js","/assets/_app.planning-DWNmhQHG.js","/assets/_app.recurring-Cj0IUW_x.js","/assets/_app.reports-DPIHZsPz.js","/assets/_app.search-BJ56Qd8k.js","/assets/_app.team-JhWKZ9OZ.js","/assets/_app.team.funds-DJ21ZoWi.js","/assets/_app.team.index-XKTuAXv7.js","/assets/_app.team.periods._periodId-DbOC_1ob.js","/assets/_app.team.periods.index-CmePFeam.js","/assets/_app.team.shares-DH8lm3zc.js","/assets/_app.transactions-C9YmDjow.js","/assets/_app.wallet-Rg6sEReA.js","/assets/accent-DdF_a61b.js","/assets/calendar-C35FAti_.js","/assets/format-P-qd1Sc3.js","/assets/icons-Bnxrkfpv.js","/assets/index-ChZVcLbp.css","/assets/index-D3rN0Ay-.js","/assets/lazyRouteComponent-Cidn-IxD.js","/assets/link-zlPc2dpQ.js","/assets/login-CpBvxCnw.js","/assets/matchContext-DMvaB68E.js","/assets/mutations-ZsxLHP9s.js","/assets/queryDefaults-CWxSrB3v.js","/assets/reports-CRTCAbn6.js","/assets/schemas-CVVp9boS.js","/assets/shared-SgmbPFvw.js","/assets/signOut-nFV7pFHN.js","/assets/status-C7SjyUYO.js","/assets/strings-BCCyY6_M.js","/assets/strings-UURT3zlX.js","/assets/surface-DzxPIoKu.js","/assets/table.styles-CZK_udqK.js","/assets/tables-DYJj8qyP.js","/assets/transport-ioNnRIQo.js","/assets/ui-ByCGzsnw.js","/assets/useActiveBook-COhPHf8b.js","/assets/useCatalog-BO6LYa0K.js","/assets/useFormValidation-D1gdg7dU.js","/assets/useHasTabbableChild-BmYEnA3O.js","/assets/useIsNarrow-DiKLqwnC.js","/assets/useMatch-DCgyN5y2.js","/assets/useNavigate-Da90IVY1.js","/assets/useRates-BOzrz4Pq.js","/assets/useRouter-CRcyIvSD.js","/assets/useSelector-Drejm5EM.js","/assets/useSlot-6BS0QQt_.js","/assets/useSpinButton-DhQrazLv.js","/assets/useTextField-BNU2gb8B.js","/assets/useToggleState-Ha15y2d2.js","/assets/useUpdateEffect-DUrXg8gH.js","/assets/with-selector-CZ8b7WQg.js"];
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
