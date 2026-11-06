import { ThemeToggle } from "@nyxon/nasim";
import { RatesTicker } from "@/features/market/RatesTicker";
import { LiveClock } from "@/shared/LiveClock";
import { t } from "@/strings";
import { Brand } from "./Brand";
import { BookSwitcher } from "./BookSwitcher";

// On a phone the bar carries the brand; with the sidebar beside it, only the book and theme.
export function TopBar({ sidebar }: { sidebar: boolean }) {
	return (
		<header className="z-20 shrink-0 border-b border-separator bg-background/85 px-page pt-(--nasim-safe-top) backdrop-blur">
			{sidebar ? (
				// A desktop: the date and time in the middle of the bar, the book on one side, the prices on the other.
				<div className="grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-4">
					<div className="justify-self-start">
						<BookSwitcher />
					</div>
					<LiveClock align="center" />
					<div className="min-w-0 justify-self-end">
						<RatesTicker />
					</div>
				</div>
			) : (
				// A phone: the mark at the start, the book in the middle, the time and theme at the end.
				<div className="grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-2">
					<div className="justify-self-start">
						<Brand iconOnly />
					</div>
					<div className="justify-self-center">
						<BookSwitcher />
					</div>
					<div className="flex items-center gap-2 justify-self-end">
						<span className="rounded-full bg-surface-secondary px-2.5 py-1">
							<LiveClock withDate={false} />
						</span>
						<ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />
					</div>
				</div>
			)}
		</header>
	);
}
