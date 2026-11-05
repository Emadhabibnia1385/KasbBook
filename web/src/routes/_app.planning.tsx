import { createFileRoute } from "@tanstack/react-router";
import { EmptyState, PageHeader } from "@nyxon/nasim";
import { t } from "@/strings";

export const Route = createFileRoute("/_app/planning")({ component: Page });

function Page() {
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.planning} />
			<EmptyState title={t.soon.title} description={t.soon.body} />
		</div>
	);
}
