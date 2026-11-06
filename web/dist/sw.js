const CACHE = "kasbbook-4930a266ef";
const FILES = ["/assets/BookRequired-BWM2OJ0z.js","/assets/BottomSheet-BXklDesD.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-DQ1MUuUw.js","/assets/Collapsible-Buo9Ymjo.js","/assets/ConfirmDialog-CVp-VuJu.js","/assets/CurrencyPicker-Ct9oRVlI.js","/assets/DataTable-DPYwO0zb.js","/assets/DayField-hTZdtPIV.js","/assets/DeveloperFooter-BQ1TMTvv.js","/assets/ErrorState-2S4BZW9M.js","/assets/FilterChips-CLk90K_b.js","/assets/FocusScope-D-iZOUJL.js","/assets/GithubLink-DeOJS5x4.js","/assets/InstallButton-CzA_WJ1j.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-r6KYQbE4.js","/assets/ManageTabs-CEugfhim.js","/assets/Modal-B4vLQ1Fg.js","/assets/Notice-CMmXpzTI.js","/assets/PageHeader-oMuC3nrp.js","/assets/PayrollPage-CvGI7mab.js","/assets/ProfileForm-C_JnpULD.js","/assets/SearchBox-DLqMPTJq.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-D6IlHpnQ.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-SRglhFc2.js","/assets/SwitchField-iggeEd25.js","/assets/Tabs-DjyaGxa1.js","/assets/TextField-j7d_o7fq.js","/assets/_app-C86xw4kt.js","/assets/_app.account-BjXlJARl.js","/assets/_app.books-DzkerCC3.js","/assets/_app.index-CZLX2LPb.js","/assets/_app.manage-CsEF4hUw.js","/assets/_app.more-2RPDzgLv.js","/assets/_app.planning-Dm55yqfU.js","/assets/_app.reports-BYbHiBR1.js","/assets/_app.team-BiM546xn.js","/assets/_app.team.funds-CXoARJ7j.js","/assets/_app.team.index-0vyj6bqi.js","/assets/_app.team.periods._periodId-CrtsCcqp.js","/assets/_app.team.periods.index-C1i1kc4a.js","/assets/_app.team.shares-CJ0nYJXH.js","/assets/_app.transactions-CDH19lnR.js","/assets/_app.wallet-j3kptmYB.js","/assets/accent-DOFH-ceJ.js","/assets/auth-B76SWViu.js","/assets/books-DK1f1yvU.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-DudiGOs5.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-C8shygRA.js","/assets/index-CrIo1sSw.css","/assets/index.esm-DNO6z4tV.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-pdvhKUgz.js","/assets/market-CGZz6g0C.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-sBbo-jlO.js","/assets/overlays-Du95Et58.js","/assets/payroll-BD0uZ_W5.js","/assets/queryDefaults-BXfqKZz8.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-2PwIN60F.js","/assets/schemas-Ct0pGj04.js","/assets/shared-C4YNthzn.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DD1Kw-YI.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-d3M8a-PE.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-D_xILXcA.js","/assets/useCatalog-BjQGfOOU.js","/assets/useHasTabbableChild-U4awNXJN.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-BDdO1pYG.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton--mUxhr-n.js","/assets/useToggleState-WvLk2rz8.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
