import { Link } from "@tanstack/react-router";
import { t } from "@/strings";

export function Brand({ full = false, iconOnly = false }: { full?: boolean; iconOnly?: boolean }) {
	return (
		<Link to="/" className="flex min-w-0 items-center gap-2 rounded-xl">
			<img src="/icons/icon-192.png" alt="" className="size-9 shrink-0" />
			<span className={`truncate text-base font-semibold ${iconOnly ? "sr-only" : ""}`}>
				{full ? `${t.brand} · ${t.tagline}` : t.brand}
			</span>
		</Link>
	);
}
