const CACHE = "kasbbook-7593fb5e2d";
const FILES = ["/assets/Charts-C7I_CuMJ.js","/assets/ChoiceFields-CZ-_Np1X.js","/assets/CollectionBuilder-T9bQDRP6.js","/assets/ConfirmDialog-Dkjm8r6h.js","/assets/DataTable-Cmv0VKFk.js","/assets/DateTimeField-B2j2c10w.js","/assets/DayField-BD7bejgu.js","/assets/DragAndDrop-Ds3ah63o.js","/assets/ErrorState-CiPpjao5.js","/assets/FilterChips-CWf0rrI7.js","/assets/FocusScope-Civ0XdoF.js","/assets/InstallButton-ByeLrbyc.js","/assets/KeyValueList-0E7q7hjz.js","/assets/Link-C2KyAG9B.js","/assets/Modal-DQdL_M8v.js","/assets/Notice--r9qVVMC.js","/assets/PageHeader--zGlgJpS.js","/assets/PayrollPage-CB4k-mh7.js","/assets/SectionCard-DG2_Rf0-.js","/assets/SelectField-MNyU8M0C.js","/assets/SelectionIndicator-BwwunOgs.js","/assets/StatusChip-DzDRbNxf.js","/assets/SwitchField-CxQwUSia.js","/assets/TextField-DbyuagEc.js","/assets/ThemeToggle-C0naAqxz.js","/assets/_app-CWXw0Gl-.js","/assets/_app.account-CcbQOxnq.js","/assets/_app.books-6uLsTY0G.js","/assets/_app.index-kgLUlpDc.js","/assets/_app.more-CYsfSkAB.js","/assets/_app.planning-CkLB9-Tf.js","/assets/_app.recurring-umGBhcBU.js","/assets/_app.reports-CKlufPpG.js","/assets/_app.search-DnYUhsuF.js","/assets/_app.team-B6owj-Ga.js","/assets/_app.team.funds-C5A86Oqh.js","/assets/_app.team.index-CBosSGAV.js","/assets/_app.team.periods._periodId-DHrq3vSQ.js","/assets/_app.team.periods.index-B4mx4er7.js","/assets/_app.team.shares-BP9BFibt.js","/assets/_app.transactions-B3aOceDd.js","/assets/_app.wallet-B-eBJbkW.js","/assets/accent-CfOHEx2n.js","/assets/calendar-C35FAti_.js","/assets/format-DupWuRm2.js","/assets/icons-Bsy-TNkW.js","/assets/index-4tc4e3jF.css","/assets/index-w8fl1_tm.js","/assets/lazyRouteComponent-ChyK7SOo.js","/assets/link-CFR5OBE4.js","/assets/login-BNT5fhRi.js","/assets/matchContext-DmgTkfSu.js","/assets/mutations-D_Jqgeny.js","/assets/queryDefaults-Bd591jUK.js","/assets/reports-BZdsjOx6.js","/assets/schemas-cORr4rl3.js","/assets/shared-D0DFdPyd.js","/assets/signOut-CdBJ1fOy.js","/assets/status-C7SjyUYO.js","/assets/strings-ClE7uIU9.js","/assets/strings-DNGbYR3T.js","/assets/surface-kV_B6eGu.js","/assets/table.styles-CflpiJqJ.js","/assets/tables-DEukPXb3.js","/assets/transport-BFJmNEOG.js","/assets/ui-Bltz5F58.js","/assets/useActiveBook-3q_LbPc1.js","/assets/useFormValidation-BG4q04Qr.js","/assets/useHasTabbableChild-Bx8KtZgS.js","/assets/useMatch-D3mnEpfI.js","/assets/useNavigate-BrX_4xaG.js","/assets/useSelector-Dw7MJ7Fo.js","/assets/useSlot-B1pbfOCQ.js","/assets/useSpinButton-kuBjLjea.js","/assets/useTextField-DIZb7_Ya.js","/assets/useToggleState-Dqy-4sSu.js","/assets/useUpdateEffect-D2l3pu2z.js","/assets/with-selector-DellVOkQ.js"];
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
