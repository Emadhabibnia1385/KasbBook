import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	ConfirmDialog,
	FormRoot,
	Modal,
	SectionCard,
	SelectField,
	SubmitButton,
	toast,
} from "@nyxon/nasim";
import {
	getIncomeListLinksQueryKey,
	useIncomeCreateLink,
	useIncomeDeleteLink,
	useIncomeEntries,
	useIncomeListLinks,
	useIncomeResync,
	useIncomeUpdateLink,
} from "@/api/generated/income/income";
import type { BookResponse, IncomeLinkResponse } from "@/api/generated/model";
import { Loaded } from "@/features/analytics/Loaded";
import { useActiveBook } from "@/features/books/useActiveBook";
import { CategoryField } from "@/features/transactions/FormControls";
import { todayIso } from "@/features/transactions/filters";
import { pickedDay, toPicker } from "@/shared/dates";
import { DayField } from "@/shared/DayField";
import { DayPair } from "@/shared/DayPair";
import { formatMoney } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";

/** «−۱۶۰ تومان» for a loss, the plain figure otherwise: a negative share is written as an expense. */
function signedMoney(value: string, currency: string): string {
	return Number(value) < 0
		? `−${formatMoney(String(Math.abs(Number(value))), currency)}`
		: formatMoney(value, currency);
}

const MODES = ["payment", "period", "daily", "weekly", "monthly"] as const;
type Mode = (typeof MODES)[number];

const schema = z.object({
	target: z.string().min(1),
	mode: z.enum(MODES),
	category: z.string().trim().max(80),
	starts_on: z.string().min(1, { error: t.days.needDate }),
});
type Values = z.input<typeof schema>;

/** A business book has no payroll: only the running modes make sense for it. */
const modesFor = (book: BookResponse): Mode[] =>
	book.type === "business" ? ["daily", "weekly", "monthly"] : [...MODES];

function LinkForm({
	book,
	targets,
	link,
	onDone,
}: {
	book: BookResponse;
	targets: BookResponse[];
	link: IncomeLinkResponse | null;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useIncomeCreateLink();
	const update = useIncomeUpdateLink();
	const available = modesFor(book);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			target: link?.target_book_id ?? targets[0]?.id ?? "",
			mode:
				(link?.mode as Mode | undefined) ?? (available.includes("payment") ? "payment" : "daily"),
			category: link?.category ?? "",
			starts_on: toPicker(link?.starts_on ?? todayIso()),
		},
	});
	const mode = useWatch({ control: form.control, name: "mode" });
	const target = useWatch({ control: form.control, name: "target" });
	// The income is filed under a category of the book it lands in; another book has its own.
	const targetBook = link?.target_book_id ?? target;
	useEffect(() => {
		if (!link) form.setValue("category", "");
	}, [target, link, form]);
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					if (link) {
						await update.mutateAsync({
							linkId: link.id,
							data: {
								mode: values.mode,
								category: values.category || link.category,
								starts_on: pickedDay(values.starts_on),
							},
						});
					} else {
						await create.mutateAsync({
							data: {
								source_book_id: book.id,
								target_book_id: values.target,
								mode: values.mode,
								category: values.category || null,
								starts_on: pickedDay(values.starts_on),
							},
						});
					}
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getIncomeListLinksQueryKey() }),
						refreshMoney(queryClient, link?.target_book_id ?? values.target),
					]);
					toast.success(t.income.saved);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			{link ? null : (
				<SelectField
					name="target"
					label={t.income.target}
					options={targets.map((target) => ({ value: target.id, label: target.name }))}
				/>
			)}
			<SelectField
				name="mode"
				label={t.income.mode}
				options={available.map((value) => ({ value, label: t.income.modes[value] }))}
			/>
			<p className="text-xs leading-relaxed text-muted">{t.income.modeHints[mode as Mode]}</p>
			{book.type === "business" ? (
				<p className="text-xs text-muted">{t.income.businessNote}</p>
			) : null}
			{targetBook ? (
				<CategoryField
					key={targetBook}
					name="category"
					bookId={targetBook}
					flow="income"
					label={t.income.category}
				/>
			) : null}
			<p className="text-xs text-muted">
				{t.income.categoryHint} <bdi>«{book.name}»</bdi>
			</p>
			<DayField name="starts_on" label={t.income.startsOn} />
			<p className="text-xs text-muted">{t.income.startsOnHint}</p>
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Entries({ link, currency }: { link: IncomeLinkResponse; currency: string }) {
	const query = useIncomeEntries(link.id);
	return (
		<div className="flex flex-col gap-1">
			<span className="text-sm font-medium">{t.income.entries}</span>
			<Loaded query={query}>
				{(rows) =>
					rows.length === 0 ? (
						<p className="text-sm text-muted">{t.income.noEntries}</p>
					) : (
						<ul className="flex flex-col">
							{rows.slice(0, 10).map((row) => (
								<li
									key={row.ref}
									className="flex flex-wrap items-center justify-between gap-2 border-b border-separator py-1.5 text-sm last:border-b-0"
								>
									<span className="flex items-center gap-2">
										<DayPair iso={row.occurred_on} bookId={link.target_book_id} inline />
										{row.problem ? (
											<span className="text-xs text-danger">{row.problem}</span>
										) : null}
									</span>
									<span
										className={Number(row.amount) < 0 ? "tabular-nums text-danger" : "tabular-nums"}
										title={Number(row.amount) < 0 ? t.income.lossShare : undefined}
									>
										{signedMoney(row.amount, currency)}
									</span>
								</li>
							))}
						</ul>
					)
				}
			</Loaded>
		</div>
	);
}

function Active({
	book,
	link,
	targets,
}: {
	book: BookResponse;
	link: IncomeLinkResponse;
	targets: BookResponse[];
}) {
	const queryClient = useQueryClient();
	const update = useIncomeUpdateLink();
	const resync = useIncomeResync();
	const remove = useIncomeDeleteLink();
	const [editing, setEditing] = useState(false);
	const [ending, setEnding] = useState<"keep" | "remove" | null>(null);
	const refresh = () =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: getIncomeListLinksQueryKey() }),
			queryClient.invalidateQueries({
				predicate: (query) => String(query.queryKey[0]).includes("/income-links"),
			}),
			refreshMoney(queryClient, link.target_book_id),
		]);
	return (
		<div className="flex flex-col gap-4">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="flex min-w-0 flex-col gap-0.5">
					<span className="font-semibold">
						<bdi>{link.target_book_name}</bdi>
						{link.is_active ? null : (
							<span className="ms-2 rounded-full bg-surface-secondary px-2 py-0.5 text-xs text-muted">
								{t.income.inactive}
							</span>
						)}
					</span>
					<span className="text-sm text-muted">{t.income.modes[link.mode as Mode]}</span>
					<span className="text-xs text-muted">
						<bdi>{link.category}</bdi>
					</span>
				</div>
				<div className="flex flex-col items-end">
					<span className="text-xs text-muted">
						{t.income.written}: {link.entries}
					</span>
					<span className="text-lg font-semibold tabular-nums">
						{signedMoney(link.total, book.currency)}
					</span>
				</div>
			</div>
			{link.problems > 0 ? (
				<p className="rounded-xl border border-danger/40 bg-danger/10 p-3 text-sm">
					{link.problems} {t.income.problems}. {t.income.problemsHint}
				</p>
			) : null}
			<Entries link={link} currency={book.currency} />
			<div className="flex flex-wrap gap-2">
				<Button size="sm" variant="secondary" onPress={() => setEditing(true)}>
					{t.income.edit}
				</Button>
				{link.is_active ? (
					<Button
						size="sm"
						variant="secondary"
						isPending={resync.isPending}
						onPress={async () => {
							try {
								await resync.mutateAsync({ linkId: link.id });
								await refresh();
								toast.success(t.income.resynced);
							} catch (error) {
								reportFailure(error);
							}
						}}
					>
						{t.income.resync}
					</Button>
				) : null}
				<Button
					size="sm"
					variant="secondary"
					onPress={async () => {
						try {
							await update.mutateAsync({ linkId: link.id, data: { is_active: !link.is_active } });
							await refresh();
						} catch (error) {
							reportFailure(error);
						}
					}}
				>
					{link.is_active ? t.income.switchOff : t.income.switchOn}
				</Button>
				<Button size="sm" variant="danger-soft" onPress={() => setEnding("keep")}>
					{t.income.end}
				</Button>
				<Button size="sm" variant="danger-soft" onPress={() => setEnding("remove")}>
					{t.income.endAndRemove}
				</Button>
			</div>
			<Modal isOpen={editing} onOpenChange={setEditing} title={t.income.edit}>
				{editing ? (
					<LinkForm book={book} targets={targets} link={link} onDone={() => setEditing(false)} />
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={ending !== null}
				onOpenChange={(open) => !open && setEnding(null)}
				title={t.income.endTitle}
				description={ending === "remove" ? t.income.endRemoveBody : t.income.endBody}
				confirmLabel={ending === "remove" ? t.income.endAndRemove : t.income.end}
				tone="danger"
				onConfirm={async () => {
					try {
						await remove.mutateAsync({
							linkId: link.id,
							params: { remove_income: ending === "remove" },
						});
						await refresh();
						toast.success(t.income.ended);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</div>
	);
}

/**
 * «ثبت درآمدم در دفتر شخصی»: on a team or business book, the one setting that carries the member's own
 * income into a book of theirs, and the list of what it has written.
 */
export function IncomePanel({ book }: { book: BookResponse }) {
	const { books } = useActiveBook();
	const links = useIncomeListLinks();
	const [adding, setAdding] = useState(false);
	// Only a personal or business book of the same unit can receive: the server also checks it is theirs.
	const targets = books.filter(
		(other) =>
			other.id !== book.id &&
			other.currency === book.currency &&
			(other.type === "personal" || other.type === "business"),
	);
	return (
		<SectionCard title={t.income.title} description={t.income.lead}>
			<Loaded query={links}>
				{(rows) => {
					const mine = rows.find((row) => row.source_book_id === book.id);
					if (mine) return <Active book={book} link={mine} targets={targets} />;
					return (
						<div className="flex flex-col gap-3">
							<p className="text-sm text-muted">
								{targets.length === 0 ? t.income.noTarget : t.income.none}
							</p>
							{targets.length > 0 ? (
								<div>
									<Button size="sm" onPress={() => setAdding(true)}>
										{t.income.enable}
									</Button>
								</div>
							) : null}
							<Modal isOpen={adding} onOpenChange={setAdding} title={t.income.title}>
								{adding ? (
									<LinkForm
										book={book}
										targets={targets}
										link={null}
										onDone={() => setAdding(false)}
									/>
								) : null}
							</Modal>
						</div>
					);
				}}
			</Loaded>
		</SectionCard>
	);
}
