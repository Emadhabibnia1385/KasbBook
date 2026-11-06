import type { ReactNode } from "react";
import { Button, EmptyState } from "@nyxon/nasim";
import type { BookResponse } from "@/api/generated/model";
import { selectBook, useActiveBook } from "@/features/books/useActiveBook";
import { t } from "@/strings";

/**
 * Assets, funds, holdings and financial notes are a person's own: a team's or a business's books have no
 * use for them. In any other kind of book this says so and offers the personal book, if there is one.
 */
export function PersonalOnly({ book, children }: { book: BookResponse; children: ReactNode }) {
	const { books } = useActiveBook();
	if (book.type === "personal") return <>{children}</>;
	const personal = books.find((item) => item.type === "personal");
	return (
		<EmptyState
			title={t.manage.personalOnlyTitle}
			description={t.manage.personalOnly}
			action={
				personal ? (
					<Button onPress={() => selectBook(personal.id)}>
						{`${t.manage.goPersonal}: ${personal.name}`}
					</Button>
				) : undefined
			}
		/>
	);
}
