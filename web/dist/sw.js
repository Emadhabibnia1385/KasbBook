const CACHE = "kasbbook-164512fe0e";
const FILES = ["/assets/BottomSheet-C4JGRfox.js","/assets/Charts-C7I_CuMJ.js","/assets/ChoiceFields-lFvGl_8c.js","/assets/CollectionBuilder-T9bQDRP6.js","/assets/ConfirmDialog-__NqmosO.js","/assets/DataTable-BerEjvMW.js","/assets/DateTimeField-Ba7OCqaT.js","/assets/DayField-CpX_ETkn.js","/assets/DragAndDrop-gsw_MYmJ.js","/assets/ErrorState-wWJaarJT.js","/assets/FilterChips-CWf0rrI7.js","/assets/FocusScope-Civ0XdoF.js","/assets/InstallButton-CuFL2NlB.js","/assets/KeyValueList-0E7q7hjz.js","/assets/Link-C2KyAG9B.js","/assets/Modal-DiEL58L3.js","/assets/Notice-BvqFSmV2.js","/assets/PageHeader-o7L-GkKi.js","/assets/PayrollPage-DdbIvF87.js","/assets/SectionCard-DG2_Rf0-.js","/assets/SelectField-BZIn1RKz.js","/assets/SelectionIndicator-BwwunOgs.js","/assets/StatusChip-CG1MEo26.js","/assets/SwitchField-BVGbo9xG.js","/assets/TextField-BkVvcaJH.js","/assets/ThemeToggle-CxuVbvfo.js","/assets/_app-B2t9A04P.js","/assets/_app.account-BvBsL-HQ.js","/assets/_app.books-DCK_gITr.js","/assets/_app.index-DTjcmYZn.js","/assets/_app.more-RpzYQM7r.js","/assets/_app.planning-D8pgZNeS.js","/assets/_app.recurring-BiZQxdTt.js","/assets/_app.reports-Cv4VB7kJ.js","/assets/_app.search-Du4cJIZF.js","/assets/_app.team-CpL64WBo.js","/assets/_app.team.funds-a7noIB26.js","/assets/_app.team.index-AGwN-ehU.js","/assets/_app.team.periods._periodId-DPArHb49.js","/assets/_app.team.periods.index-DPgE7GwG.js","/assets/_app.team.shares-mVVBtvH2.js","/assets/_app.transactions-DwQ3ZpKY.js","/assets/_app.wallet-11j2o7bA.js","/assets/accent-Dt6R8Uka.js","/assets/calendar-C35FAti_.js","/assets/format-DupWuRm2.js","/assets/icons-Bsy-TNkW.js","/assets/index-4tc4e3jF.css","/assets/index-DZBZQ2QI.js","/assets/lazyRouteComponent-ChyK7SOo.js","/assets/link-CFR5OBE4.js","/assets/login-DbrigrSl.js","/assets/matchContext-DmgTkfSu.js","/assets/mutations-BMGTQTdc.js","/assets/queryDefaults-D_ZD4LMn.js","/assets/reports-uwDkn6-j.js","/assets/schemas-YFbNprMQ.js","/assets/shared-D396Rzq2.js","/assets/signOut-DDCx9Mp8.js","/assets/status-C7SjyUYO.js","/assets/strings-ClE7uIU9.js","/assets/strings-DNGbYR3T.js","/assets/surface-kV_B6eGu.js","/assets/table.styles-CflpiJqJ.js","/assets/tables-CcGc4nSU.js","/assets/transport-BFJmNEOG.js","/assets/ui-Bltz5F58.js","/assets/useActiveBook-BgkeswL3.js","/assets/useFormValidation-2OqhsF_j.js","/assets/useHasTabbableChild-Bx8KtZgS.js","/assets/useMatch-D3mnEpfI.js","/assets/useNavigate-BrX_4xaG.js","/assets/useSelector-Dw7MJ7Fo.js","/assets/useSlot-B1pbfOCQ.js","/assets/useSpinButton-CO0i7cBm.js","/assets/useTextField-BR5mGMfH.js","/assets/useToggleState-Dqy-4sSu.js","/assets/useUpdateEffect-D2l3pu2z.js","/assets/with-selector-DellVOkQ.js"];
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
