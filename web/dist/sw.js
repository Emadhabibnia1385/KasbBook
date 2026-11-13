const CACHE = "kasbbook-0e40f9603a";
const FILES = ["/assets/AttachmentsField-DFv8C3jE.js","/assets/BookRequired-BEIhld3Y.js","/assets/BottomSheet-BmM3_iRc.js","/assets/BrandMark-Blbq77Vm.js","/assets/Capital-VPdLCNIj.js","/assets/Charts-BojqsdNm.js","/assets/ChoiceFields-Cy2ctAWt.js","/assets/Collapsible-DZdoHJm3.js","/assets/ConfirmDialog-bmoH2Iot.js","/assets/CurrencyPicker-CybaYAaC.js","/assets/DataTable-6AufL6Uq.js","/assets/DayField-Y-YHrgmD.js","/assets/DayPair-QsZLBmPJ.js","/assets/FilterChips-Bl5Ht3io.js","/assets/KeyValueList-FsR-dbFQ.js","/assets/Loaded-DkXovm5I.js","/assets/ManageTabs-Bf5weHjb.js","/assets/Modal-D_LkxvjI.js","/assets/Notice-DPyhJZqE.js","/assets/PageHeader-tE-wnShS.js","/assets/PayrollPage-Bdy4JRSs.js","/assets/ProfileForm-CsJeqFZ9.js","/assets/SearchBox-fV1G0hIU.js","/assets/SectionCard-BKlaMgai.js","/assets/SelectField-DBmfUXRq.js","/assets/SelectionIndicator-C9QVPS_Y.js","/assets/Spinner-cqd9rOB0.js","/assets/StatCard-Cw-YZCc0.js","/assets/StatusChip-ypT53tEz.js","/assets/SwitchField-BM5gzYUp.js","/assets/Tabs-DBGZvp4E.js","/assets/TextField-h5Qno9e-.js","/assets/_app-DZ19Gdk-.js","/assets/_app.account-CRS49afL.js","/assets/_app.books-2ZazNFdK.js","/assets/_app.index-BK1qX8SJ.js","/assets/_app.manage-DzVoBrNZ.js","/assets/_app.planning-7vx7lxWg.js","/assets/_app.portfolio-p9mJj57X.js","/assets/_app.reports-CipVpHTl.js","/assets/_app.team-CysDp5xD.js","/assets/_app.team.funds-CYj02Rrr.js","/assets/_app.team.index-BwUIpc49.js","/assets/_app.team.periods._periodId-wIkEBM5E.js","/assets/_app.team.periods.index-hV9Ou7R5.js","/assets/_app.transactions-DibPnUsr.js","/assets/_app.wallet-hIewDZlu.js","/assets/accent-CHFAhO5A.js","/assets/auth-BNg6hhrY.js","/assets/books-uiJKTvFl.js","/assets/button-5crzzCDg.js","/assets/calendar-CSrm6Fth.js","/assets/charts-BkjHxvr2.js","/assets/clock-TdFq1o9U.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/format-WJzb05Q7.js","/assets/icons-DVqTy1-C.js","/assets/index-BDmsjWeE.js","/assets/index-CC_CXbGk.css","/assets/index.esm-aNmlkMUd.js","/assets/lazyRouteComponent-B7a2lAOC.js","/assets/link-DZy9PmPz.js","/assets/login-C2enrpEH.js","/assets/market-DmUMNz7f.js","/assets/matchContext-kazl_cX3.js","/assets/mutations-Bt5ua3aB.js","/assets/payroll-DlJO5NnE.js","/assets/portfolio-DZNZxxn5.js","/assets/reports-CRkftf90.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-RPVDhI2N.js","/assets/schemas-93JDjIo0.js","/assets/shared-BA6Y4l-z.js","/assets/status-C7SjyUYO.js","/assets/table.styles-DB7iyIQ1.js","/assets/tables-C1gZjFL_.js","/assets/tickerPrefs-D4nJKjKj.js","/assets/transactions-CC0SzSmo.js","/assets/ui-DcmSD2au.js","/assets/useActiveBook-CymxxHgW.js","/assets/useCatalog-4NFECLxB.js","/assets/useHasTabbableChild-CC0Bhzqa.js","/assets/useIsNarrow-Cr47XORv.js","/assets/useLocation-Bpef0XH5.js","/assets/useMatch-CHPLZIaT.js","/assets/useNavigate-M13Ot55A.js","/assets/useQuotes-IgdEdyrQ.js","/assets/useSlot-CT-fj3zG.js","/assets/useSpinButton-BK9o1IrR.js","/assets/useTickerRows-DiPyMFnb.js","/assets/useToggleState-CuyqCZ-d.js","/assets/useUpdateEffect-Bqm2MYY9.js","/assets/with-selector-BkG2LxgK.js"];
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
