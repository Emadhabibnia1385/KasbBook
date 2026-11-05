const CACHE = "kasbbook-19082f1cb7";
const FILES = ["/assets/BottomSheet-DiYVS3XS.js","/assets/Charts-DZWAPvDp.js","/assets/ChoiceFields-D_0PAd0R.js","/assets/Collapsible-BR5pSzDa.js","/assets/CollectionBuilder-BigIRBza.js","/assets/ConfirmDialog-DyB8lKGt.js","/assets/DataTable-COVx7LT-.js","/assets/DateTimeField-BSGWHxvy.js","/assets/DayField-BaU59H9X.js","/assets/DragAndDrop-1R7ek6_L.js","/assets/ErrorState-uB-56Ofq.js","/assets/FilterChips-kFw2Gl2t.js","/assets/FocusScope-BgOQhTPB.js","/assets/InstallButton-k1Cz1byu.js","/assets/KeyValueList-DM1vJoEX.js","/assets/Link-B6sq4z1i.js","/assets/Modal-BhF708tH.js","/assets/Notice-B95dbP7o.js","/assets/PageHeader-CkonKY7H.js","/assets/PayrollPage-o56ZdGO6.js","/assets/SectionCard-O5l0mxB8.js","/assets/SelectField-D6G8GsR2.js","/assets/SelectionIndicator-hZkl0qy3.js","/assets/StatusChip-DbZm1STV.js","/assets/SwitchField-K0qx9Rat.js","/assets/TextField-D0PiNM5m.js","/assets/ThemeToggle-t26OHq_K.js","/assets/_app-Bn98a3xn.js","/assets/_app.account-oRqHppaf.js","/assets/_app.books-Cqh1edjF.js","/assets/_app.index-B62lOW7a.js","/assets/_app.more-CA7grDk7.js","/assets/_app.planning-MkZQoV3_.js","/assets/_app.recurring-7dUhhYSV.js","/assets/_app.reports-DRY6N7D3.js","/assets/_app.search-DZax1Gbc.js","/assets/_app.team-L80-HnlN.js","/assets/_app.team.funds-BJg8DT0Y.js","/assets/_app.team.index-C1my40gj.js","/assets/_app.team.periods._periodId-NArvq11t.js","/assets/_app.team.periods.index-D-y8cRI-.js","/assets/_app.team.shares-CzrIoGtZ.js","/assets/_app.transactions-BXg6QUq5.js","/assets/_app.wallet-C2hZE_-W.js","/assets/accent-D6IL8dM3.js","/assets/calendar-C35FAti_.js","/assets/format-DupWuRm2.js","/assets/icons-DFgabhjq.js","/assets/index-CfXKEty4.css","/assets/index-DJap0krZ.js","/assets/lazyRouteComponent-BsljRddL.js","/assets/link-BbUtCKq0.js","/assets/login-DI2ht1l5.js","/assets/matchContext-HMXR2XpX.js","/assets/mutations-Cd3XI-YO.js","/assets/queryDefaults-B1kNmTlz.js","/assets/reports-Dwv6LQI0.js","/assets/schemas-BTZiu_E4.js","/assets/shared-BLn8aAzf.js","/assets/signOut-CU4ATT-p.js","/assets/status-C7SjyUYO.js","/assets/strings-BQcxtGjp.js","/assets/strings-DT4akK7p.js","/assets/surface-CzA7T0kx.js","/assets/table.styles-C9ZXqndc.js","/assets/tables-DFMIGkJ1.js","/assets/transport-BCEDyp1I.js","/assets/ui-oGGszYwm.js","/assets/useActiveBook-Cez9QPAS.js","/assets/useFormValidation-240P3Knz.js","/assets/useHasTabbableChild-B8Md5FYT.js","/assets/useIsNarrow-BXxJdJrb.js","/assets/useMatch-DYibeXvc.js","/assets/useNavigate-CZulIm_s.js","/assets/useSelector-Zgotc0U6.js","/assets/useSlot-CLqMz7-X.js","/assets/useSpinButton-CVQ9Yery.js","/assets/useTextField-9skw0TnH.js","/assets/useToggleState-CSK3MIj-.js","/assets/useUpdateEffect-BchlkYDO.js","/assets/with-selector-BIzQSWzc.js"];
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
