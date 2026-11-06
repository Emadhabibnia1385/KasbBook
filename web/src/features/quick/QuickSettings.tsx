import { SettingGroup } from "@/shared/SettingGroup";
import { t } from "@/strings";
import { setQuickEnabled, useQuickEnabled } from "./quickPrefs";

/** Whether the round quick-actions button is shown on this device. */
export function QuickSettings() {
	const enabled = useQuickEnabled();
	const { enable, enableHint } = t.quick;
	return (
		<SettingGroup title={t.quick.open}>
			<label
				aria-label={enable}
				className="flex min-h-12 cursor-pointer items-center justify-between gap-3"
			>
				<span className="flex flex-col">
					<span className="text-sm font-medium">{enable}</span>
					<span className="text-xs text-muted">{enableHint}</span>
				</span>
				<input
					type="checkbox"
					className="size-5 shrink-0 accent-(--accent)"
					checked={enabled}
					onChange={(event) => setQuickEnabled(event.target.checked)}
				/>
			</label>
		</SettingGroup>
	);
}
