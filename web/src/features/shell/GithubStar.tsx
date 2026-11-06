import { useEffect, useState } from "react";
import { t } from "@/strings";

const REPO = "Emadhabibnia1385/KasbBook";
const KEY = "kasbbook.stars";
const HOUR = 3_600_000;

// GitHub allows 60 anonymous requests an hour per address, and a count that is an hour old is as good as a
// live one, so it is asked for at most once an hour per device and remembered.
function cached(): number | null {
	try {
		const raw = localStorage.getItem(KEY);
		const saved = raw ? (JSON.parse(raw) as { count: number; at: number }) : null;
		return saved && Date.now() - saved.at < HOUR ? saved.count : null;
	} catch {
		return null;
	}
}

function useStars(): number | null {
	const [count, setCount] = useState<number | null>(cached);
	useEffect(() => {
		if (cached() !== null) return;
		let alive = true;
		fetch(`https://api.github.com/repos/${REPO}`)
			.then((response) => (response.ok ? response.json() : null))
			.then((body: { stargazers_count?: number } | null) => {
				if (!alive || typeof body?.stargazers_count !== "number") return;
				setCount(body.stargazers_count);
				try {
					localStorage.setItem(
						KEY,
						JSON.stringify({ count: body.stargazers_count, at: Date.now() }),
					);
				} catch {
					// the count is shown this once and asked for again next time
				}
			})
			.catch(() => {
				// offline or rate-limited: the button works without a number
			});
		return () => {
			alive = false;
		};
	}, []);
	return count;
}

/** GitHub's own Star button, as a link to the repository, with the live count beside it. */
export function GithubStar() {
	const count = useStars();
	return (
		<a
			href={`https://github.com/${REPO}`}
			target="_blank"
			rel="noopener noreferrer"
			aria-label={t.github.label}
			dir="ltr"
			className="inline-flex h-8 items-stretch overflow-hidden rounded-md border border-border bg-surface text-xs font-semibold transition-colors hover:bg-surface-secondary"
		>
			<span className="flex items-center gap-1.5 px-2.5">
				<svg aria-hidden viewBox="0 0 16 16" className="size-4 fill-current">
					<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
				</svg>
				{t.github.star}
			</span>
			{count !== null ? (
				<span className="flex items-center border-s border-border bg-background px-2.5 tabular-nums">
					{count.toLocaleString("en-US")}
				</span>
			) : null}
		</a>
	);
}
