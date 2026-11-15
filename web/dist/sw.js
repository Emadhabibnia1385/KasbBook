const CACHE = "kasbbook-bc8ccdb61d";
const FILES = ["/assets/AttachmentsField-uSPRkIDz.js","/assets/BookRequired-C7te3rCX.js","/assets/BottomSheet-DXeRNeAB.js","/assets/BrandMark-DykBUC2e.js","/assets/Capital-Cz08-dJl.js","/assets/Charts-BojqsdNm.js","/assets/ChoiceFields-BAVaFctB.js","/assets/Collapsible-DchkJ3cN.js","/assets/ConfirmDialog-kS067LDV.js","/assets/CurrencyPicker-CD1w4rEY.js","/assets/DataTable-C7r3gJjh.js","/assets/DayField-DTo_MQ2L.js","/assets/DayPair-Bz6yCzTH.js","/assets/FilterChips-Bl5Ht3io.js","/assets/KeyValueList-FsR-dbFQ.js","/assets/Loaded-Ckw6GaK7.js","/assets/ManageTabs-_puP-hRX.js","/assets/Modal-DqV7k6zX.js","/assets/Notice-CLMjpJeG.js","/assets/PageHeader-H-GVqVDy.js","/assets/PayrollPage-Bg3jqAHp.js","/assets/ProfileForm-VoT-ajJF.js","/assets/SearchBox-BndhrpXN.js","/assets/SectionCard-BKlaMgai.js","/assets/SelectField-D5mGhDQB.js","/assets/SelectionIndicator-C9QVPS_Y.js","/assets/Spinner-cqd9rOB0.js","/assets/StatCard-Cw-YZCc0.js","/assets/StatusChip-DSHvfXjj.js","/assets/SwitchField-CHOoJsc4.js","/assets/Tabs-B7z3lTcD.js","/assets/TextField-B3tSVxBL.js","/assets/_app-Cb_gmWl2.js","/assets/_app.account-DRPzCVEy.js","/assets/_app.books-B4qwi7uz.js","/assets/_app.index-BMYabGK8.js","/assets/_app.manage-daaiVB1z.js","/assets/_app.planning-BK64hyw7.js","/assets/_app.portfolio-Dl55upfc.js","/assets/_app.reports-BPG1aIUx.js","/assets/_app.team-Cq0llHE_.js","/assets/_app.team.funds-DAnMcpRa.js","/assets/_app.team.index-DS3ZCy7l.js","/assets/_app.team.periods._periodId-BsKsHrHw.js","/assets/_app.team.periods.index-X78H08uU.js","/assets/_app.transactions-DPGS2uJY.js","/assets/_app.wallet-DOOWmaeg.js","/assets/accent-DPKhTJhA.js","/assets/auth-jwR7pXRa.js","/assets/books-DJ_-36Je.js","/assets/button-5crzzCDg.js","/assets/calendar-CSrm6Fth.js","/assets/charts-Cb_4C5u7.js","/assets/clock-TdFq1o9U.js","/assets/decimal-CFE_Ny-g.js","/assets/decimal-CMCVxv2Z.js","/assets/format-D9ou2Yt5.js","/assets/icons-DVqTy1-C.js","/assets/index-CC_CXbGk.css","/assets/index-DirqhS-s.js","/assets/index.esm-DrmIP2NT.js","/assets/lazyRouteComponent-B7a2lAOC.js","/assets/link-DZy9PmPz.js","/assets/login-eyJKDxBq.js","/assets/market-uK4EG1-D.js","/assets/matchContext-kazl_cX3.js","/assets/mutations-BcFpz3vh.js","/assets/payroll-DtWo1pCP.js","/assets/portfolio-CGzPSzbH.js","/assets/reports-Cyrg2_uF.js","/assets/rolldown-runtime-XKyaHtl9.js","/assets/rules-zQa8TmLT.js","/assets/schemas-BiNZVqZU.js","/assets/shared-Zoi0a4GR.js","/assets/status-C7SjyUYO.js","/assets/table.styles-DB7iyIQ1.js","/assets/tables-C_tnZHba.js","/assets/tickerPrefs-Yc4lH71t.js","/assets/transactions-C-csBTsg.js","/assets/ui-DyirVomd.js","/assets/useActiveBook-E9yAs0bW.js","/assets/useCatalog-Be-GH2et.js","/assets/useHasTabbableChild-CC0Bhzqa.js","/assets/useIsNarrow-Cr47XORv.js","/assets/useLocation-Bpef0XH5.js","/assets/useMatch-CHPLZIaT.js","/assets/useNavigate-M13Ot55A.js","/assets/useQuotes-C4eduh4t.js","/assets/useSlot-CT-fj3zG.js","/assets/useSpinButton-D4vBMFBQ.js","/assets/useTickerRows-Cl-vo5YG.js","/assets/useToggleState-CuyqCZ-d.js","/assets/useUpdateEffect-Bqm2MYY9.js","/assets/with-selector-BkG2LxgK.js"];
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
