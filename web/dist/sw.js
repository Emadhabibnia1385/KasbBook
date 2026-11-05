const CACHE = "kasbbook-f12b06c28a";
const FILES = ["/assets/Charts-BU31UJ-o.js","/assets/ChoiceFields-CFzOEn4z.js","/assets/CollectionBuilder-iYIjSQgx.js","/assets/ConfirmDialog-C8jsrWRc.js","/assets/DataTable-B7c1BnFp.js","/assets/DateTimeField-CL6apKD0.js","/assets/DayField-CQq3_DJ0.js","/assets/ErrorState-BxX_yjSM.js","/assets/InstallButton-B2mchSUS.js","/assets/KeyValueList-DQjWeKqM.js","/assets/Link-BX1Gvggx.js","/assets/Modal-PZY_wrna.js","/assets/Notice-C161p7xk.js","/assets/PageHeader-u8SoRPrE.js","/assets/PayrollPage-BWd169J9.js","/assets/SectionCard-9S6_l6Xi.js","/assets/SelectField-BoGIdJpH.js","/assets/StatCard-B-qZ1xUx.js","/assets/StatusChip-DeOSOBd0.js","/assets/SwitchField-KpUbE3RR.js","/assets/TextField-Dsq_0puD.js","/assets/ThemeToggle-ClxtJc7Q.js","/assets/_app-CI-m5F_i.js","/assets/_app.account-lPD2N0hK.js","/assets/_app.books-C274ny5r.js","/assets/_app.index-Dbz15d_D.js","/assets/_app.more-Bmv-jBO8.js","/assets/_app.planning-lNtjKkRx.js","/assets/_app.recurring-vRKru43t.js","/assets/_app.reports-BllhV_w4.js","/assets/_app.search-CwKTvkxp.js","/assets/_app.team-BZJeOaUF.js","/assets/_app.team.funds-CG_ejwYR.js","/assets/_app.team.index-Ce4f6Fjm.js","/assets/_app.team.periods._periodId-OJNuIxAt.js","/assets/_app.team.periods.index-DBfp6v09.js","/assets/_app.team.shares-DU9R7E9E.js","/assets/_app.transactions-CsNUANEM.js","/assets/_app.wallet-DHpm345k.js","/assets/accent-O9Hpz4lQ.js","/assets/calendar-C35FAti_.js","/assets/format-BPk_mNU9.js","/assets/icons-BlOr8WdH.js","/assets/index-CH9E0Elv.css","/assets/index-D0Gk0HCZ.js","/assets/lazyRouteComponent-DdWrl9AU.js","/assets/link-DdIhdplL.js","/assets/login-Cxp7OWkg.js","/assets/matchContext-NjudlW8v.js","/assets/mutations-tFsPCg9M.js","/assets/queryDefaults-CsP2awnf.js","/assets/reports-CoIZdxkT.js","/assets/schemas-C1FmFL2Y.js","/assets/shared-CQN8QEO4.js","/assets/shim-8txr7G6_.js","/assets/signOut-CK6ubh0T.js","/assets/status-C7SjyUYO.js","/assets/strings-C-eu09Qg.js","/assets/strings-DPobDfMS.js","/assets/surface-DdYtZqje.js","/assets/table.styles-COPRjo9F.js","/assets/transport-DnGEoAoO.js","/assets/ui-OIFySGL2.js","/assets/useActiveBook-DMlyTEBe.js","/assets/useFormValidation-yYTsuVGZ.js","/assets/useHasTabbableChild-YOECMOcJ.js","/assets/useMatch-XJmWTNFe.js","/assets/useNavigate-uWk5B5j0.js","/assets/useSelector-CoLMyxrS.js","/assets/useSlot-CNZxew1J.js","/assets/useSpinButton-Bgt4wkVq.js","/assets/useTextField-DJprgQmC.js","/assets/useUpdateEffect-BiC1Fhpw.js"];
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
