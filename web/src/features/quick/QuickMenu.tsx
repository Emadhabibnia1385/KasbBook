import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "@nyxon/nasim";
import { SIDE_NAV } from "@/app/shell/nav";
import {
	BoltIcon,
	BookIcon,
	CloseIcon,
	FolderIcon,
	MoonIcon,
	PlusIcon,
	SunIcon,
} from "@/shared/icons";
import { t } from "@/strings";
import { openQuick } from "./quickBus";
import { useQuickEnabled } from "./quickPrefs";

// The places, grouped under headings so a long list reads as a few short ones.
const GROUPS: { title: string; to: string[] }[] = [
	{ title: t.nav.groupMoney, to: ["/", "/transactions", "/reports", "/planning"] },
	{ title: t.nav.groupManage, to: ["/team", "/books", "/wallet", "/recurring"] },
	{ title: t.nav.groupAccount, to: ["/account"] },
];

const row =
	"quick-item flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-start text-sm font-medium transition-colors hover:bg-surface-secondary focus-visible:bg-surface-secondary";

/**
 * A round button at the edge of the page that opens the things done most: record an entry, add a category
 * or a book, switch light and dark, and a door to every section. It can be switched off in the settings.
 */
export function QuickMenu() {
	const enabled = useQuickEnabled();
	const [open, setOpen] = useState(false);
	const navigate = useNavigate();
	const { scheme, setMode } = useTheme();
	const panel = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
		window.addEventListener("keydown", onKey);
		// The first action takes the focus, so the keyboard can use the menu straight away.
		panel.current?.querySelector<HTMLElement>("button, a")?.focus();
		return () => window.removeEventListener("keydown", onKey);
	}, [open]);

	if (!enabled) return null;
	const act = (run: () => void) => () => {
		setOpen(false);
		run();
	};
	const dark = scheme === "dark";
	// Each row rises a beat after the one before it.
	const delay = (index: number) => ({ animationDelay: `${Math.min(index, 14) * 28}ms` });

	return (
		<>
			{open ? (
				<button
					type="button"
					tabIndex={-1}
					aria-label={t.quick.close}
					className="fixed inset-0 z-40 cursor-default bg-black/30 backdrop-blur-[1px]"
					onClick={() => setOpen(false)}
				/>
			) : null}
			<div className="fixed end-3 bottom-[calc(var(--nasim-bottom-bar,0rem)+6.5rem)] z-40 flex flex-col items-end gap-3 lg:bottom-6">
				{open ? (
					<section
						ref={panel}
						aria-label={t.quick.open}
						className="quick-panel flex max-h-[70dvh] w-[min(20rem,calc(100vw-1.5rem))] flex-col gap-1 overflow-y-auto overscroll-contain rounded-3xl border border-border bg-surface p-2 shadow-overlay"
					>
						<p className="px-3 pt-2 pb-1 text-xs font-semibold text-muted">{t.quick.ops}</p>
						<button
							type="button"
							className={row}
							style={delay(0)}
							onClick={act(() => openQuick("transaction"))}
						>
							<PlusIcon aria-hidden className="size-5 text-accent" />
							{t.quick.addTransaction}
						</button>
						<button
							type="button"
							className={row}
							style={delay(1)}
							onClick={act(() => openQuick("category"))}
						>
							<FolderIcon aria-hidden className="size-5 text-accent" />
							{t.quick.addCategory}
						</button>
						<button
							type="button"
							className={row}
							style={delay(2)}
							onClick={act(() => void navigate({ to: "/books", search: { new: "IRT" } }))}
						>
							<BookIcon aria-hidden className="size-5 text-accent" />
							{t.quick.addBook}
						</button>
						<button
							type="button"
							className={row}
							style={delay(3)}
							onClick={act(() => setMode(dark ? "light" : "dark"))}
						>
							{dark ? (
								<SunIcon aria-hidden className="size-5 text-accent" />
							) : (
								<MoonIcon aria-hidden className="size-5 text-accent" />
							)}
							{dark ? t.quick.toLight : t.quick.toDark}
						</button>
						{GROUPS.map((group, groupIndex) => (
							<div key={group.title} className="flex flex-col gap-1 border-t border-separator pt-1">
								<p className="px-3 pt-1 pb-0.5 text-xs font-semibold text-muted">{group.title}</p>
								{group.to.map((to, position) => {
									const offset =
										4 + GROUPS.slice(0, groupIndex).reduce((sum, g) => sum + g.to.length, 0);
									const item = SIDE_NAV.find((candidate) => candidate.to === to);
									if (!item) return null;
									return (
										<button
											key={to}
											type="button"
											className={row}
											style={delay(offset + position)}
											onClick={act(() => void navigate({ to: item.to }))}
										>
											<item.icon aria-hidden className="size-5 text-muted" />
											{item.label}
										</button>
									);
								})}
							</div>
						))}
					</section>
				) : null}
				<button
					type="button"
					aria-expanded={open}
					aria-label={open ? t.quick.close : t.quick.open}
					className={`quick-fab ${open ? "quick-fab-open" : ""} relative grid size-12 place-items-center lg:size-14 rounded-full bg-accent text-accent-foreground shadow-lg outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2`}
					onClick={() => setOpen((value) => !value)}
				>
					{open ? (
						<CloseIcon aria-hidden className="size-7" />
					) : (
						<BoltIcon aria-hidden className="quick-bolt size-7" />
					)}
				</button>
			</div>
		</>
	);
}
