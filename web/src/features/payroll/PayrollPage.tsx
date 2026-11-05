import { EmptyState, PageSkeleton } from "@nyxon/nasim";
import type { ReactNode } from "react";
import type { BookResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";
import { isPayrollBook } from "./shared";

/** The pages of the payroll area all start the same way: a book that can run payroll, or the reason it can not. */
export function PayrollPage({ children }: { children: (book: BookResponse) => ReactNode }) {
	const { book, isLoading } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (!book)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	if (!isPayrollBook(book))
		return <EmptyState as="h1" title={t.payroll.teamOnlyTitle} description={t.payroll.teamOnly} />;
	return <>{children(book)}</>;
}
