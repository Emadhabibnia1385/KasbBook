const CACHE = "kasbbook-06d5488028";
const FILES = ["/assets/BookRequired-Wwq7UMpB.js","/assets/BottomSheet-DcAsQg-B.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-Bpxr-11a.js","/assets/Collapsible-BUG6LNxa.js","/assets/ConfirmDialog-BK7UYYkG.js","/assets/CurrencyPicker-C-80A2zc.js","/assets/DataTable-AvesdMZC.js","/assets/DayField-DJU3qmLi.js","/assets/DeveloperFooter-BCHcUm8A.js","/assets/ErrorState-BMr9HXYe.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-BHMWn9n_.js","/assets/InstallButton-CTLXogXY.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-gdaPA4Ux.js","/assets/ManageTabs-D88XJta_.js","/assets/Modal-DlyG7AJu.js","/assets/Notice-CiBfy2Uy.js","/assets/PageHeader-5df0VXAO.js","/assets/PayrollPage-DP9KCqPM.js","/assets/ProfileForm-DZzdYE-2.js","/assets/SearchBox-B4d9H2Cz.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-DfKfNU1u.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-pK9Zlclv.js","/assets/SwitchField-DlUsuKDy.js","/assets/Tabs-BoLYGjMx.js","/assets/TextField-Dm0LBZHr.js","/assets/_app-v1wVYdMI.js","/assets/_app.account-DXiCa8Y7.js","/assets/_app.books-B-537f7E.js","/assets/_app.index-Be6Bw49v.js","/assets/_app.manage-CPxjwjGW.js","/assets/_app.more-BVbXffbD.js","/assets/_app.planning-D4Ds3G9z.js","/assets/_app.reports-BDaVcq2d.js","/assets/_app.team-CsLFbR8Q.js","/assets/_app.team.funds-D-qa8dkJ.js","/assets/_app.team.index-ogRJRSDj.js","/assets/_app.team.periods._periodId-BzZPeg1e.js","/assets/_app.team.periods.index-c4SZbDR5.js","/assets/_app.team.shares-CG0WF5WA.js","/assets/_app.transactions-CdtRoyVg.js","/assets/_app.wallet-CHa_TFLD.js","/assets/accent-Bj87VWeQ.js","/assets/auth-DvmTHQoW.js","/assets/books-4AmToSLK.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-D2NsgclS.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-Bj8UpKx1.js","/assets/index-CrIo1sSw.css","/assets/index.esm-DKS9QDFy.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-EKsRV2O9.js","/assets/market-GoXTmoDg.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-n8hKf0jp.js","/assets/overlays-DG77hsuE.js","/assets/payroll-CE593gUP.js","/assets/queryDefaults-BTT5kfvI.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-Dgp6nsiC.js","/assets/schemas-OZVmd9EV.js","/assets/shared-D9cwddes.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-Z5cCv8aV.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-DjtvbsrO.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-BI72owcl.js","/assets/useCatalog-DpR36uEw.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-rjtl7yHq.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-De6dQ2Vq.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
