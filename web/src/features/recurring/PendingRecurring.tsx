import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, FormRoot, Modal, SectionCard, SubmitButton, TextField, toast } from "@nyxon/nasim";
import {
	getRecurringListPendingEverywhereQueryKey,
	getRecurringListPendingQueryKey,
	useRecurringConfirmOccurrence,
	useRecurringListPending,
	useRecurringListPendingEverywhere,
	useRecurringSkipOccurrence,
} from "@/api/generated/recurring/recurring";
import type { BookResponse, PendingOccurrenceResponse } from "@/api/generated/model";
import { formatDay, formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

const schema = z.object({
	amount: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
			error: t.repeat.badAmount,
		}),
});
type Values = z.input<typeof schema>;

function AmountForm({
	row,
	onSubmit,
}: {
	row: PendingOccurrenceResponse;
	onSubmit: (amount: string) => Promise<void>;
}) {
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { amount: String(Number(row.amount)) },
	});
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => onSubmit(schema.parse(raw).amount)}
		>
			<p className="text-sm text-muted">{t.repeat.amountLead}</p>
			<TextField
				name="amount"
				label={t.repeat.amountLabel}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SubmitButton>{t.repeat.confirm}</SubmitButton>
		</FormRoot>
	);
}

/**
 * Repeating transactions whose date has come and that ask first: each waits here for a yes (recorded on
 * its own day, with its amount changed if need be) or a no. Nothing shows when nothing is waiting.
 */
export function PendingRecurring({ book }: { book: BookResponse | undefined }) {
	const queryClient = useQueryClient();
	const single = useRecurringListPending(book?.id ?? "", {
		query: { enabled: book !== undefined },
	});
	const every = useRecurringListPendingEverywhere({ query: { enabled: book === undefined } });
	const rows = (book ? single.data : every.data) ?? [];
	const confirm = useRecurringConfirmOccurrence();
	const skip = useRecurringSkipOccurrence();
	const [busy, setBusy] = useState<string | null>(null);
	const [other, setOther] = useState<PendingOccurrenceResponse | null>(null);

	const refresh = async (bookId: string) => {
		await Promise.all([
			queryClient.invalidateQueries({ queryKey: getRecurringListPendingQueryKey(bookId) }),
			queryClient.invalidateQueries({ queryKey: getRecurringListPendingEverywhereQueryKey() }),
			refreshMoney(queryClient, bookId),
		]);
	};
	const answer = async (row: PendingOccurrenceResponse, run: () => Promise<void>, done: string) => {
		setBusy(row.id);
		try {
			await run();
			await refresh(row.book_id);
			toast.success(done);
		} catch (error) {
			reportFailure(error);
			throw error;
		} finally {
			setBusy(null);
		}
	};

	if (rows.length === 0) return null;
	return (
		<SectionCard title={t.repeat.pendingTitle} description={t.repeat.pendingLead}>
			<ul className="flex flex-col gap-2">
				{rows.map((row) => (
					<li
						key={row.id}
						className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3 sm:flex-row sm:items-center"
					>
						<span className="flex min-w-0 flex-1 flex-col gap-0.5">
							<span className="flex items-baseline gap-2">
								<b className="truncate">{row.category}</b>
								<span className="text-xs text-muted">{formatDay(row.due_on)}</span>
								{book ? null : <bdi className="truncate text-xs text-muted">{row.book_name}</bdi>}
							</span>
							<span className={`font-semibold ${row.flow === "income" ? "text-success" : ""}`}>
								{row.flow === "income" ? "+" : "−"}
								{formatMoney(row.amount, row.currency)}
							</span>
						</span>
						<span className="flex flex-wrap items-center gap-2">
							<Button
								size="sm"
								isPending={busy === row.id}
								onPress={() =>
									void answer(
										row,
										() =>
											confirm
												.mutateAsync({ bookId: row.book_id, occurrenceId: row.id, data: {} })
												.then(() => undefined),
										t.repeat.confirmed,
									).catch(() => undefined)
								}
							>
								{t.repeat.confirm}
							</Button>
							<Button size="sm" variant="secondary" onPress={() => setOther(row)}>
								{t.repeat.otherAmount}
							</Button>
							<Button
								size="sm"
								variant="ghost"
								isDisabled={busy === row.id}
								onPress={() =>
									void answer(
										row,
										() =>
											skip
												.mutateAsync({ bookId: row.book_id, occurrenceId: row.id })
												.then(() => undefined),
										t.repeat.skipped,
									).catch(() => undefined)
								}
							>
								{t.repeat.skip}
							</Button>
						</span>
					</li>
				))}
			</ul>
			<Modal
				isOpen={other !== null}
				onOpenChange={(open) => !open && setOther(null)}
				title={t.repeat.amountTitle}
				size="sm"
			>
				{other ? (
					<AmountForm
						key={other.id}
						row={other}
						onSubmit={async (amount) => {
							await answer(
								other,
								() =>
									confirm
										.mutateAsync({
											bookId: other.book_id,
											occurrenceId: other.id,
											data: { amount },
										})
										.then(() => undefined),
								t.repeat.confirmed,
							).then(
								() => setOther(null),
								() => undefined,
							);
						}}
					/>
				) : null}
			</Modal>
		</SectionCard>
	);
}
