import { SectionCard } from "@nyxon/nasim";
import { HeaderSettings } from "@/features/market/HeaderSettings";
import { TickerSettings } from "@/features/market/TickerSettings";
import { QuickSettings } from "@/features/quick/QuickSettings";
import { t } from "@/strings";

/** Everything about how the panel looks and what it shows, in one card: quick actions, the top bar, the price strip. */
export function Customize() {
	return (
		<SectionCard title={t.acct.customizeTitle} description={t.acct.customizeLead}>
			<div className="flex flex-col">
				<QuickSettings />
				<HeaderSettings />
				<TickerSettings />
			</div>
		</SectionCard>
	);
}
