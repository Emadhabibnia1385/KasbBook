import { t } from "@/strings";
import { DEVELOPER_URL, GithubMark } from "./GithubLink";

/** The credit line, kept at the foot of the page: the developer's name in English, linked to their GitHub. */
export function DeveloperFooter() {
	return (
		<footer className="flex shrink-0 items-center justify-center gap-2 border-t border-border bg-background px-page py-2 text-xs text-muted">
			<span>{t.footer.developedBy}</span>
			<a
				href={DEVELOPER_URL}
				target="_blank"
				rel="noopener noreferrer"
				dir="ltr"
				className="inline-flex items-center gap-1.5 font-medium text-foreground hover:underline"
			>
				<GithubMark className="size-4" />
				{t.footer.developer}
			</a>
		</footer>
	);
}
