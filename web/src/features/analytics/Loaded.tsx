import { Button, LoadingState } from "@nyxon/nasim";
import type { ReactNode } from "react";
import { t } from "@/strings";

type Query<T> = {
	isLoading: boolean;
	isError: boolean;
	data: T | undefined;
	refetch: () => unknown;
};

/** One panel's data: a spinner while it loads, a retry where it failed, and the panel once it is here. */
export function Loaded<T>({
	query,
	children,
}: {
	query: Query<T>;
	children: (data: T) => ReactNode;
}) {
	if (query.isLoading) return <LoadingState size="inline" />;
	if (query.isError || query.data === undefined) {
		return (
			<div className="flex flex-col items-start gap-2 py-2">
				<p className="text-sm text-muted">{t.errors.body}</p>
				<Button variant="secondary" size="sm" onPress={() => void query.refetch()}>
					{t.common.retry}
				</Button>
			</div>
		);
	}
	return <>{children(query.data)}</>;
}
