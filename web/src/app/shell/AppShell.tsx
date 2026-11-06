import type { ReactNode } from "react";
import { tv } from "tailwind-variants";
import { OfflineBanner, useMediaQuery } from "@nyxon/nasim";
import { AutoTimezone } from "@/features/account/AutoTimezone";
import { useCatalog } from "@/features/currencies/useCatalog";
import { QuickHost } from "@/features/quick/QuickHost";
import { QuickMenu } from "@/features/quick/QuickMenu";
import { DeveloperFooter } from "@/features/shell/DeveloperFooter";
import { GuestBar } from "@/features/shell/GuestBar";
import { t } from "@/strings";
import { DesktopSidebar } from "./DesktopSidebar";
import { PhoneTabBar } from "./PhoneTabBar";
import { TopBar } from "./TopBar";

const shell = tv({
	slots: {
		root: "flex h-dvh overflow-hidden bg-background text-foreground",
		skip: "sr-only z-50 rounded-xl bg-surface px-4 py-3 text-sm font-medium shadow-overlay focus:not-sr-only focus:fixed focus:start-4 focus:top-4",
		column: "flex min-w-0 flex-1 flex-col",
		main: "min-h-0 flex-1 overflow-y-auto overscroll-contain px-page outline-none",
		// The room under the content keeps the last rows clear of the round quick-actions button.
		page: "mx-auto w-full max-w-6xl pt-4 pb-28",
	},
});

// A sidebar from 1024px wide, bars around the page below it: the top one with the book and theme,
// the bottom one with the daily destinations. A tablet gets whichever its width earns.
export function AppShell({ children }: { children: ReactNode }) {
	const wide = useMediaQuery("(min-width: 1024px)");
	// Fetched once per visit so every amount can name its currency in Persian.
	useCatalog();
	const { root, skip, column, main, page } = shell();
	return (
		<div className={root()}>
			<a href="#main" className={skip()}>
				{t.nav.skip}
			</a>
			{wide ? <DesktopSidebar /> : null}
			<div className={column()}>
				<TopBar sidebar={wide} />
				<OfflineBanner>{t.common.offline}</OfflineBanner>
				<GuestBar />
				<main id="main" tabIndex={-1} className={main()}>
					<div className={page()}>{children}</div>
				</main>
				<DeveloperFooter />
				{wide ? null : <PhoneTabBar />}
			</div>
			<QuickMenu />
			<QuickHost />
			<AutoTimezone />
		</div>
	);
}
