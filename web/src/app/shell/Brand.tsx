import { Link } from "@tanstack/react-router";
import { t } from "@/strings";
import { BrandMark } from "./BrandMark";

// The mark and the name; the tagline sits under the name in small type instead of squeezing the name out of
// a narrow sidebar. On a phone only the mark shows, and the name is kept for screen readers.
export function Brand({ full = false, iconOnly = false }: { full?: boolean; iconOnly?: boolean }) {
	return (
		<Link to="/" className="flex min-w-0 items-center gap-2 rounded-xl">
			<BrandMark className="size-9 shrink-0" />
			<span className={iconOnly ? "sr-only" : "flex min-w-0 flex-col leading-tight"}>
				<span className="truncate text-base font-bold">{t.brand}</span>
				{full ? <span className="text-xs font-normal text-muted">{t.tagline}</span> : null}
			</span>
		</Link>
	);
}
