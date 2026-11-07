const CACHE = "kasbbook-7b214ad860";
const FILES = ["/assets/AttachmentsField-t5IyWhnJ.js","/assets/BookRequired-DNQabBJF.js","/assets/BottomSheet-Cz6z0-nU.js","/assets/Capital-DBlLuOiL.js","/assets/Charts-DOWm0FYw.js","/assets/ChoiceFields-xPPP8y5e.js","/assets/Collapsible-Cgoe9GIP.js","/assets/ConfirmDialog-C3SW2BKf.js","/assets/CurrencyPicker-CoM1QRbm.js","/assets/DataTable-XrViza42.js","/assets/DayField-ByDMTDoh.js","/assets/DeveloperFooter-vljxDXfw.js","/assets/ErrorState-CnDXSx85.js","/assets/FilterChips-BHfhfI4o.js","/assets/FocusScope-DL5ULG5T.js","/assets/KeyValueList-O19IKbWA.js","/assets/Loaded-DJxpDFzv.js","/assets/ManageTabs-Bswkklf6.js","/assets/Modal-DodWdfOD.js","/assets/Notice-BeqTXSk6.js","/assets/PayrollPage-2VRBF5p9.js","/assets/ProfileForm-lQ2kdWAs.js","/assets/SearchBox-CNxwYuey.js","/assets/SectionCard-D8a4uU46.js","/assets/SelectField-BbxicF7U.js","/assets/SelectionIndicator-Bj9juco5.js","/assets/Spinner-CEQuEC3Y.js","/assets/StatCard-DzcC3Dyn.js","/assets/StatusChip-DjE01bE5.js","/assets/SwitchField-CdLsbjIX.js","/assets/Tabs-J3EO8ome.js","/assets/TextField-DMqQdfl5.js","/assets/_app-v2JG6AGb.js","/assets/_app.account-BOvlKWtn.js","/assets/_app.books-kqeXmlJU.js","/assets/_app.index-u7wTZIMj.js","/assets/_app.manage-CoDUADvy.js","/assets/_app.planning-CrY9qeYp.js","/assets/_app.portfolio-rNaMzU6t.js","/assets/_app.reports-DFDwJEGr.js","/assets/_app.team-Z1kNIVRP.js","/assets/_app.team.funds-Ca_AycfZ.js","/assets/_app.team.index-BuKqki4t.js","/assets/_app.team.periods._periodId-DvdpjaZO.js","/assets/_app.team.periods.index-Gfk1_4-6.js","/assets/_app.team.shares-D5ZDizI4.js","/assets/_app.transactions-Ca551Vhd.js","/assets/_app.wallet-D_4vXe8Y.js","/assets/accent-YMdxc2Qq.js","/assets/auth-CwPEKYWb.js","/assets/books-DD6pPbhm.js","/assets/button-DYe9f7tS.js","/assets/calendar-CSrm6Fth.js","/assets/charts-jHT6EV1Q.js","/assets/clock-pHA8QHUR.js","/assets/decimal-6YOdUFZ2.js","/assets/decimal-DOCnKjJ4.js","/assets/icons-B7FYk1y3.js","/assets/index-B3yjPaDs.js","/assets/index-BrecVvEy.css","/assets/index.esm-CB1CYBo3.js","/assets/lazyRouteComponent-BZYlobv8.js","/assets/link-Bk6kg8xw.js","/assets/login-uqlz6MlA.js","/assets/market-p-QU-xI5.js","/assets/matchContext-DlNeQ2JE.js","/assets/mutations-CGEOocAL.js","/assets/payroll-BGkMfsDP.js","/assets/portfolio-B2kkmOZL.js","/assets/queryDefaults-soUFNPRM.js","/assets/reports-ibKYkmfl.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-BFi3dGPG.js","/assets/schemas-HsB4BCrl.js","/assets/shared-CTWQdoUG.js","/assets/status-C7SjyUYO.js","/assets/table.styles-BRB1DKDZ.js","/assets/tables-L9OwDXpE.js","/assets/tickerPrefs-DXBnbwas.js","/assets/transactions-BMwmEubP.js","/assets/ui-B3RTC1gR.js","/assets/useActiveBook-9LzqQ7qr.js","/assets/useCatalog-nT0M7o3y.js","/assets/useHasTabbableChild-sUKxCnkx.js","/assets/useIsNarrow-Bj3kOTYG.js","/assets/useLocation-DZF2D5EK.js","/assets/useMatch-BYMt7ZyH.js","/assets/useNavigate-C10A5PKi.js","/assets/useQuotes-DYqwp0Df.js","/assets/useSlot-BEiQ00Pd.js","/assets/useSpinButton-CIzvENRF.js","/assets/useTickerRows-B_ouGvd1.js","/assets/useToggleState-BHHhO3Fm.js","/assets/useUpdateEffect-B-5IqvTE.js","/assets/with-selector-DwG_6BnE.js"];
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
