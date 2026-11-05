import { EmptyState } from "@nyxon/nasim";
import { t } from "@/strings";

export function NotFound() {
	return <EmptyState as="h1" title={t.errors.notFound} action={{ label: t.errors.home, href: "/" }} />;
}
