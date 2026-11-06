import { Button } from "@nyxon/nasim";
import { SettingGroup } from "@/shared/SettingGroup";
import { t } from "@/strings";
import { type HeaderPrefs, resetHeaderPrefs, setHeaderPref, useHeaderPrefs } from "./headerPrefs";

const PARTS: { key: keyof HeaderPrefs; label: string; hint?: string }[] = [
	{ key: "time", label: t.headerSettings.time },
	{ key: "weekday", label: t.headerSettings.weekday },
	{ key: "jalali", label: t.headerSettings.jalali },
	{ key: "gregorian", label: t.headerSettings.gregorian },
	{ key: "prices", label: t.headerSettings.prices, hint: t.headerSettings.pricesHint },
];

/** Which parts of the bar at the top of the page are shown. */
export function HeaderSettings() {
	const prefs = useHeaderPrefs();
	return (
		<SettingGroup title={t.headerSettings.title} description={t.headerSettings.description}>
			<ul className="flex flex-col">
				{PARTS.map((part) => (
					<li key={part.key} className="border-b border-separator last:border-b-0">
						<label className="flex min-h-12 cursor-pointer items-center justify-between gap-3">
							<span className="flex flex-col">
								<span className="text-sm font-medium">{part.label}</span>
								{part.hint ? <span className="text-xs text-muted">{part.hint}</span> : null}
							</span>
							<input
								type="checkbox"
								className="size-5 shrink-0 accent-(--accent)"
								checked={prefs[part.key]}
								onChange={(event) => setHeaderPref(part.key, event.target.checked)}
							/>
						</label>
					</li>
				))}
			</ul>
			<Button size="sm" variant="ghost" className="mt-2" onPress={resetHeaderPrefs}>
				{t.headerSettings.reset}
			</Button>
		</SettingGroup>
	);
}
