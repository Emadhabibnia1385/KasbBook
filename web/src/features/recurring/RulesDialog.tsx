import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ConfirmDialog, Modal, StatusChip, toast } from "@nyxon/nasim";
import {
	getRecurringListRulesQueryKey,
	useRecurringDeleteRule,
	useRecurringListRules,
	useRecurringToggleRule,
	useRecurringUpdateRule,
} from "@/api/generated/recurring/recurring";
import type { BookResponse, RecurringResponse } from "@/api/generated/model";
import { formatFullDate, formatMoney } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

function Rule({ book, rule }: { book: BookResponse; rule: RecurringResponse }) {
	const queryClient = useQueryClient();
	const toggle = useRecurringToggleRule();
	const update = useRecurringUpdateRule();
	const remove = useRecurringDeleteRule();
	const [removing, setRemoving] = useState(false);
	const asks = rule.mode === "ask";
	const refresh = () =>
		queryClient.invalidateQueries({ queryKey: getRecurringListRulesQueryKey(book.id) });
	const run = async (action: () => Promise<unknown>, done: string) => {
		try {
			await action();
			await refresh();
			toast.success(done);
		} catch (error) {
			reportFailure(error);
		}
	};
	return (
		<li className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-3">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<span className="font-medium">{rule.category}</span>
				<span className="flex items-center gap-2">
					<StatusChip
						tone={asks ? "info" : "neutral"}
						label={asks ? t.repeat.askBadge : t.repeat.autoBadge}
					/>
					<StatusChip
						tone={rule.is_active ? "success" : "warning"}
						label={rule.is_active ? t.recurring.active : t.recurring.paused}
					/>
				</span>
			</div>
			<p className={`font-semibold ${rule.flow === "income" ? "text-success" : ""}`}>
				{rule.flow === "income" ? "+" : "−"}
				{formatMoney(rule.amount, book.currency)}
			</p>
			<p className="text-sm text-muted">
				{t.repeat.periods[rule.period as keyof typeof t.repeat.periods] ?? rule.period} ·{" "}
				{t.repeat.nextOn} {formatFullDate(rule.next_run_on)}
			</p>
			{rule.description ? <p className="text-sm text-muted">{rule.description}</p> : null}
			<div className="flex flex-wrap gap-2">
				<Button
					size="sm"
					variant="secondary"
					isPending={toggle.isPending}
					onPress={() =>
						void run(
							() => toggle.mutateAsync({ bookId: book.id, ruleId: rule.id }),
							t.recurring.toggled,
						)
					}
				>
					{rule.is_active ? t.recurring.pause : t.recurring.resume}
				</Button>
				<Button
					size="sm"
					variant="secondary"
					isPending={update.isPending}
					onPress={() =>
						void run(
							() =>
								update.mutateAsync({
									bookId: book.id,
									ruleId: rule.id,
									data: { mode: asks ? "auto" : "ask" },
								}),
							t.repeat.modeChanged,
						)
					}
				>
					{asks ? t.repeat.toAuto : t.repeat.toAsk}
				</Button>
				<Button size="sm" variant="ghost" onPress={() => setRemoving(true)}>
					{t.common.delete}
				</Button>
			</div>
			<ConfirmDialog
				isOpen={removing}
				onOpenChange={setRemoving}
				title={t.recurring.deleteTitle}
				description={t.recurring.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					await run(
						() => remove.mutateAsync({ bookId: book.id, ruleId: rule.id }),
						t.recurring.deleted,
					);
				}}
			/>
		</li>
	);
}

function RulesOfBook({ book, showName }: { book: BookResponse; showName: boolean }) {
	const { data = [], isLoading } = useRecurringListRules(book.id);
	return (
		<section className="flex flex-col gap-2">
			{showName ? <h3 className="text-sm font-semibold text-muted">{book.name}</h3> : null}
			{isLoading ? null : data.length === 0 ? (
				<p className="text-sm text-muted">{t.repeat.noRules}</p>
			) : (
				<ul className="grid gap-2 md:grid-cols-2">
					{data.map((rule) => (
						<Rule key={rule.id} book={book} rule={rule} />
					))}
				</ul>
			)}
		</section>
	);
}

/** The repeating transactions already defined, with a way to pause, switch between asking and automatic, or delete. */
export function RulesDialog({
	books,
	isOpen,
	onOpenChange,
}: {
	books: BookResponse[];
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
}) {
	return (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={t.repeat.rulesTitle} size="lg">
			<div className="flex flex-col gap-4">
				<p className="text-sm text-muted">{t.repeat.rulesLead}</p>
				{books.map((book) => (
					<RulesOfBook key={book.id} book={book} showName={books.length > 1} />
				))}
			</div>
		</Modal>
	);
}
