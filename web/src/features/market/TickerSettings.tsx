import { useState } from "react";
import { Button } from "@nyxon/nasim";
import { SettingGroup } from "@/shared/SettingGroup";
import { CurrencyPicker } from "@/features/currencies/CurrencyPicker";
import { currencyName } from "@/shared/format";
import { t } from "@/strings";
import { DEFAULT_TICKER, MAX_TICKER, setTickerCodes, useTickerCodes } from "./tickerPrefs";

/** Which currencies the price strip at the top lists; any in the catalog, up to six. */
export function TickerSettings() {
	const codes = useTickerCodes();
	const [picking, setPicking] = useState(false);
	const full = codes.length >= MAX_TICKER;
	return (
		<SettingGroup title={t.tickerSettings.title} description={t.tickerSettings.description}>
			<ul className="flex flex-wrap gap-2" aria-label={t.tickerSettings.title}>
				{codes.map((code) => (
					<li
						key={code}
						className="flex items-center gap-1 rounded-full border border-border bg-surface ps-3 pe-1"
					>
						<span className="text-sm font-medium">{currencyName(code)}</span>
						<span dir="ltr" className="text-xs text-muted">
							{code}
						</span>
						<Button
							isIconOnly
							size="sm"
							variant="ghost"
							aria-label={`${t.common.delete}: ${currencyName(code)}`}
							isDisabled={codes.length <= 1}
							onPress={() => setTickerCodes(codes.filter((entry) => entry !== code))}
						>
							×
						</Button>
					</li>
				))}
			</ul>
			<div className="mt-3 flex flex-wrap gap-2">
				<Button size="sm" isDisabled={full} onPress={() => setPicking(true)}>
					{full ? t.tickerSettings.full : t.tickerSettings.add}
				</Button>
				<Button size="sm" variant="ghost" onPress={() => setTickerCodes(DEFAULT_TICKER)}>
					{t.tickerSettings.reset}
				</Button>
			</div>
			<CurrencyPicker
				isOpen={picking}
				onOpenChange={setPicking}
				title={t.tickerSettings.add}
				disabled={Object.fromEntries(codes.map((code) => [code, t.tickerSettings.already]))}
				onPick={(code) => setTickerCodes([...codes, code])}
			/>
		</SettingGroup>
	);
}
