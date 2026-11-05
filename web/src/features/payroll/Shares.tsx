import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	Notice,
	PageHeader,
	PageSkeleton,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import { useBooksListMembers } from "@/api/generated/books/books";
import type { BookResponse, MemberResponse, ShareResponse } from "@/api/generated/model";
import {
	usePayrollClearShare,
	usePayrollListShares,
	usePayrollSetShare,
} from "@/api/generated/payroll/payroll";
import { formatAmount, formatFullDate, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";
import { fromUnits, isPositive, plain, sum, toUnits } from "./decimal";
import { PayrollPage } from "./PayrollPage";
import { refreshPayroll, reportError, shareBasisLabel, shareValueText } from "./shared";
import { Figure, ItemCard } from "./ui";

// The bot offers these five; `project` exists on the server but nothing measures it yet.
const BASES = (["percent", "fixed", "hours", "days", "points"] as const).map((value) => ({
	value,
	label: t.payroll.shareBasis[value],
}));

// A percentage, a weight and an amount are all plain numbers here: «۵۰م» is not fifty million percent.
const schema = z.object({
	basis: z
		.string({ error: t.payroll.shares.needBasis })
		.min(1, { error: t.payroll.shares.needBasis }),
	value: z
		.string()
		.transform(toAscii)
		.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && isPositive(value), {
			error: t.payroll.shares.badValue,
		}),
});
type Values = z.input<typeof schema>;

function valueCopy(basis: string) {
	if (basis === "percent")
		return { label: t.payroll.shares.valuePercent, hint: t.payroll.shares.hintPercent };
	if (basis === "fixed")
		return { label: t.payroll.shares.valueFixed, hint: t.payroll.shares.hintFixed };
	return { label: t.payroll.shares.valueWeight, hint: t.payroll.shares.hintWeight };
}

function ShareForm({
	book,
	member,
	current,
	onDone,
}: {
	book: BookResponse;
	member: MemberResponse;
	current?: ShareResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const setShare = usePayrollSetShare();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			basis: current?.basis ?? "percent",
			value: current ? plain(current.value) : "",
		},
	});
	const copy = valueCopy(useWatch({ control: form.control, name: "basis" }));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await setShare.mutateAsync({
						bookId: book.id,
						data: { user_id: member.user_id, basis: values.basis, value: values.value },
					});
					await refreshPayroll(queryClient, book.id);
					toast.success(t.payroll.saved);
					onDone();
				} catch (error) {
					reportError(error);
				}
			}}
		>
			<SelectField
				name="basis"
				label={t.payroll.shares.basis}
				description={t.payroll.shares.basisHelp}
				options={BASES}
			/>
			<TextField
				name="value"
				label={copy.label}
				description={copy.hint}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Summary({ shares }: { shares: readonly ShareResponse[] }) {
	const percents = shares.filter((share) => share.basis === "percent").map((share) => share.value);
	if (percents.length === 0) return null;
	const total = sum(percents);
	const rest = fromUnits(100n * 10_000n - toUnits(total));
	return (
		<div className="flex flex-col gap-2">
			<p className="text-sm text-muted">
				{t.payroll.shares.percentTotal}: <Figure>{formatAmount(total)}٪</Figure>
			</p>
			{toUnits(total) > 100n * 10_000n ? (
				<Notice tone="warning">{t.payroll.shares.over}</Notice>
			) : toUnits(total) < 100n * 10_000n ? (
				<Notice tone="info">
					{t.payroll.shares.under} {formatAmount(rest)}٪
				</Notice>
			) : null}
		</div>
	);
}

function Members({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const members = useBooksListMembers(book.id);
	const shares = usePayrollListShares(book.id);
	const clear = usePayrollClearShare();
	const [editing, setEditing] = useState<MemberResponse | null>(null);
	const [clearing, setClearing] = useState<MemberResponse | null>(null);

	if (members.isLoading || shares.isLoading) return <PageSkeleton header={false} rows={3} />;
	if (members.isError || shares.isError) {
		return <ErrorState onRetry={() => void Promise.all([members.refetch(), shares.refetch()])} />;
	}
	const rules = new Map((shares.data ?? []).map((share) => [share.user_id, share]));
	const money = (value: string) => formatMoney(value, book.currency);

	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.nav.team} description={book.name} />
			<SectionCard title={t.payroll.shares.title} description={t.payroll.shares.lead}>
				{members.data?.length ? (
					<div className="flex flex-col gap-4">
						<ul className="grid gap-3 md:grid-cols-2">
							{members.data.map((member) => {
								const rule = rules.get(member.user_id);
								return (
									<ItemCard
										key={member.user_id}
										title={member.display_name}
										aside={
											rule ? (
												<StatusChip tone="info" label={shareBasisLabel(rule.basis)} />
											) : (
												<StatusChip tone="neutral" label={t.payroll.shares.unset} />
											)
										}
										actions={
											<>
												<Button size="sm" variant="secondary" onPress={() => setEditing(member)}>
													{rule ? t.payroll.shares.change : t.payroll.shares.set}
												</Button>
												{rule ? (
													<Button size="sm" variant="ghost" onPress={() => setClearing(member)}>
														{t.payroll.shares.clear}
													</Button>
												) : null}
											</>
										}
									>
										{rule ? (
											<p className="text-sm">
												<Figure>{shareValueText(rule.basis, rule.value, money)}</Figure>
												<span className="text-muted">
													{" · "}
													{t.payroll.shares.since} {formatFullDate(rule.effective_from)}
												</span>
											</p>
										) : null}
									</ItemCard>
								);
							})}
						</ul>
						<Summary shares={shares.data ?? []} />
					</div>
				) : (
					<EmptyState title={t.payroll.noMembers} />
				)}
			</SectionCard>

			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={`${t.payroll.shares.formTitle} ${editing?.display_name ?? ""}`}
				size="sm"
			>
				{editing ? (
					<ShareForm
						key={editing.user_id}
						book={book}
						member={editing}
						current={rules.get(editing.user_id)}
						onDone={() => setEditing(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={clearing !== null}
				onOpenChange={(open) => !open && setClearing(null)}
				title={t.payroll.shares.clearTitle}
				description={`${clearing?.display_name ?? ""}. ${t.payroll.shares.clearBody}`}
				confirmLabel={t.payroll.shares.clear}
				tone="danger"
				onConfirm={async () => {
					if (!clearing) return;
					try {
						await clear.mutateAsync({ bookId: book.id, memberUserId: clearing.user_id });
						await refreshPayroll(queryClient, book.id);
						toast.success(t.payroll.shares.cleared);
					} catch (error) {
						reportError(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

export function Shares() {
	return <PayrollPage>{(book) => <Members book={book} />}</PayrollPage>;
}
