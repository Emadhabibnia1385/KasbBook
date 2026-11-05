import { ThemeToggle } from "@nyxon/nasim";
import { RatesTicker } from "@/features/market/RatesTicker";
import { LiveClock } from "@/shared/LiveClock";
import { t } from "@/strings";
import { Brand } from "./Brand";
import { BookSwitcher } from "./BookSwitcher";

// On a phone the bar carries the brand; with the sidebar beside it, only the book and theme.
export function TopBar({ sidebar }: { sidebar: boolean }) {
	return (
		<header className="z-20 shrink-0 border-b border-separator bg-background px-page pt-(--nasim-safe-top)">
			<div className="flex h-14 items-center justify-between gap-3">
				{sidebar ? (
					<div className="flex min-w-0 items-center gap-5">
						<BookSwitcher />
						<RatesTicker />
					</div>
				) : (
					<Brand iconOnly />
				)}
				<div className="flex items-center gap-3">
					<LiveClock withDate={sidebar} />
					{sidebar ? null : <BookSwitcher />}
					{sidebar ? null : <ThemeToggle lightLabel={t.theme.light} darkLabel={t.theme.dark} />}
				</div>
			</div>
		</header>
	);
}
