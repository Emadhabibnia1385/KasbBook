const CACHE = "kasbbook-8a7847daea";
const FILES = ["/assets/BookRequired-CQxwtSq8.js","/assets/BottomSheet-DgZL80PG.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-CYO1dwi4.js","/assets/ConfirmDialog-DtwYJ3_H.js","/assets/CurrencyPicker-CULupDvH.js","/assets/DataTable-DuhMF4ib.js","/assets/DateTimeField-D4FKqtsP.js","/assets/DayField-Dpi_6f1N.js","/assets/DeveloperFooter-D53L6RrA.js","/assets/ErrorState-D9LOfpfL.js","/assets/FilterChips-DWWQ7A3p.js","/assets/FocusScope-DL5ULG5T.js","/assets/GithubLink-sAOohkEl.js","/assets/InstallButton-CJ3An9ni.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DoNOCy3f.js","/assets/ManageTabs-2CfdsLsp.js","/assets/Modal-fdad06wN.js","/assets/Notice-Dh50wEPI.js","/assets/PageHeader-C1Fg7uyf.js","/assets/PayrollPage-BNXcr58Z.js","/assets/ProfileForm-CwPXOE_R.js","/assets/SearchBox-Ih6y2W8t.js","/assets/SectionCard-BpvPY21_.js","/assets/SelectField-D8h0wG2x.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/StatusChip-7hyFsVCn.js","/assets/SwitchField-Dx4f6lqL.js","/assets/TextField-C73n-luO.js","/assets/_app-ByyK3HD5.js","/assets/_app.account-CDLyuXS2.js","/assets/_app.books-bU8RrqK_.js","/assets/_app.index-CreYAcJL.js","/assets/_app.manage-B6hVdlX0.js","/assets/_app.more-CYV01v_z.js","/assets/_app.planning-DTB92N6i.js","/assets/_app.recurring-_6glenX1.js","/assets/_app.reports-B4sD2Zo_.js","/assets/_app.team-Dt3Lqmhv.js","/assets/_app.team.funds-Cr5oWhoS.js","/assets/_app.team.index-BUNJQr6e.js","/assets/_app.team.periods._periodId-fT_Vje8E.js","/assets/_app.team.periods.index-CTvEU1An.js","/assets/_app.team.shares-30GVkwmc.js","/assets/_app.transactions-C-szp5hD.js","/assets/_app.wallet-CmuLwu8K.js","/assets/accent-1tnlOVjh.js","/assets/auth-C7qJiqww.js","/assets/books-TjOf3mHO.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/format-C27EsAeY.js","/assets/format-yhtkESqM.js","/assets/icons-DXTTqhFB.js","/assets/index-BRHQdDcn.js","/assets/index-N7RkEWUb.css","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-CVyK-NpZ.js","/assets/market-CeCg0bEu.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-DtsuWGmy.js","/assets/overlays-TBbox_D9.js","/assets/payroll-BpNzUQZS.js","/assets/queryDefaults-BT-VmJ_2.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-CCnT3w6l.js","/assets/schemas-D_0vroe-.js","/assets/shared-w1pGpPYJ.js","/assets/status-C7SjyUYO.js","/assets/strings-CdubY5B9.js","/assets/surface-q3sbrrsJ.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-DEHG4L0z.js","/assets/tickerPrefs-iFl5y9IY.js","/assets/transactions-IBU_-UKR.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-haaAxOag.js","/assets/useCatalog-CxQuwsxA.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-NGqkvO76.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-C7MsqZl3.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
