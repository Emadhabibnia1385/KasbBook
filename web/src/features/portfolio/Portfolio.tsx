import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
	Button,
	ConfirmDialog,
	ErrorState,
	Modal,
	PageHeader,
	PageSkeleton,
	SectionCard,
	StatCard,
	toast,
} from "@nyxon/nasim";
import {
	getPortfolioListNotesQueryKey,
	getPortfolioPortfolioQueryKey,
	usePortfolioDeleteEntry,
	usePortfolioDeleteHolding,
	usePortfolioDeleteNote,
	usePortfolioInstruments,
	usePortfolioListNotes,
	usePortfolioPortfolio,
} from "@/api/generated/portfolio/portfolio";
import type {
	BookResponse,
	FinancialNoteResponse,
	NoteEntryResponse,
	InstrumentResponse,
	PortfolioHoldingResponse,
} from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { PersonalOnly } from "@/features/manage/PersonalOnly";
import { BookRequired } from "@/features/books/BookRequired";
import { ManageTabs } from "@/features/manage/ManageTabs";
import { Donut, categoryColor } from "@/shared/charts";
import { formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { EntryForm, HoldingForm, NoteForm } from "./PortfolioForms";

const Figure = ({ children }: { children: string }) => (
	<span className="text-lg sm:text-xl">{children}</span>
);

/** «+۱۴٪» or «−۳٪» in the colour of a gain or a loss. */
function Result({
	value,
	base,
	percent,
}: {
	value: string;
	base: string;
	percent?: string | null;
}) {
	const n = Number(value);
	const good = n >= 0;
	return (
		<b dir="ltr" className={good ? "text-success" : "text-danger"}>
			{good ? "+" : "−"}
			{formatMoney(String(Math.abs(n)), base)}
			{percent ? ` (${good ? "+" : "−"}${formatAmount(Math.abs(Number(percent)))}٪)` : ""}
		</b>
	);
}

function Holdings({
	book,
	instruments,
}: {
	book: BookResponse;
	instruments: InstrumentResponse[];
}) {
	const queryClient = useQueryClient();
	const { data, isLoading } = usePortfolioPortfolio(book.id);
	const remove = usePortfolioDeleteHolding();
	const [adding, setAdding] = useState(false);
	const [editing, setEditing] = useState<PortfolioHoldingResponse | null>(null);
	const [removing, setRemoving] = useState<PortfolioHoldingResponse | null>(null);
	const rows = data?.holdings ?? [];
	const slices = rows
		.filter((row) => row.value && Number(row.value) > 0)
		.map((row, index) => ({
			key: row.id,
			label: row.name,
			value: String(row.value),
			color: categoryColor(index),
		}));
	return (
		<>
			{data ? (
				<div className="flex flex-col gap-2">
					<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
						<StatCard
							label={t.portfolio.total}
							value={<Figure>{formatMoney(data.total_value, data.currency)}</Figure>}
						/>
						<StatCard
							label={t.portfolio.cost}
							value={<Figure>{formatMoney(data.total_cost, data.currency)}</Figure>}
						/>
						<StatCard
							label={t.portfolio.profit}
							value={
								<span className="text-lg sm:text-xl">
									<Result value={data.total_profit} base={data.currency} />
								</span>
							}
						/>
						<StatCard
							label={t.portfolio.unpriced}
							value={<Figure>{formatAmount(data.unpriced)}</Figure>}
						/>
					</div>
					<p className="text-xs text-muted">{t.portfolio.onlyWithCost}</p>
				</div>
			) : null}
			<SectionCard
				title={t.portfolio.holdings}
				actions={
					<Button size="sm" onPress={() => setAdding(true)}>
						{t.portfolio.add}
					</Button>
				}
			>
				{isLoading ? null : rows.length === 0 ? (
					<p className="text-sm text-muted">{t.portfolio.none}</p>
				) : (
					<div className="flex flex-col gap-4">
						{slices.length > 1 ? (
							<Donut
								title={t.portfolio.holdings}
								hideTitle
								summary={t.portfolio.total}
								slices={slices}
								formatValue={(value: string) => formatMoney(value, book.currency)}
							/>
						) : null}
						<ul className="grid gap-3 md:grid-cols-2">
							{rows.map((row) => (
								<li
									key={row.id}
									className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3"
								>
									<div className="flex items-center justify-between gap-2">
										<span className="font-medium">{row.name}</span>
										<span className="text-sm text-muted">
											{formatAmount(Number(row.quantity))} {row.unit}
										</span>
									</div>
									{row.value ? (
										<p className="text-lg font-semibold">{formatMoney(row.value, book.currency)}</p>
									) : (
										<p className="text-sm text-muted">{t.portfolio.noPrice}</p>
									)}
									{row.price ? (
										<p className="text-xs text-muted">
											{t.portfolio.priceNow}: {formatMoney(row.price, book.currency)}
											{row.exact ? "" : ` · ${t.portfolio.estimate}`}
										</p>
									) : null}
									{row.cost ? (
										<p className="text-sm text-muted">
											{t.portfolio.costOf}: {formatMoney(row.cost, book.currency)}
											{row.profit ? (
												<>
													{" · "}
													<Result
														value={row.profit}
														base={book.currency}
														percent={row.profit_percent}
													/>
												</>
											) : null}
										</p>
									) : null}
									{row.note ? <p className="text-xs text-muted">{row.note}</p> : null}
									<div className="flex gap-2">
										<Button size="sm" variant="secondary" onPress={() => setEditing(row)}>
											{t.portfolio.edit}
										</Button>
										<Button size="sm" variant="ghost" onPress={() => setRemoving(row)}>
											{t.common.delete}
										</Button>
									</div>
								</li>
							))}
						</ul>
					</div>
				)}
			</SectionCard>
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.portfolio.add} size="md">
				<HoldingForm book={book} instruments={instruments} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				title={editing?.name ?? ""}
				size="md"
			>
				{editing ? (
					<HoldingForm
						key={editing.id}
						book={book}
						instruments={instruments}
						holding={editing}
						onDone={() => setEditing(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.portfolio.deleteTitle}
				description={t.portfolio.deleteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, holdingId: removing.id });
						await queryClient.invalidateQueries({
							queryKey: getPortfolioPortfolioQueryKey(book.id),
						});
						toast.success(t.portfolio.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</>
	);
}

function Note({ book, note }: { book: BookResponse; note: FinancialNoteResponse }) {
	const queryClient = useQueryClient();
	const removeNote = usePortfolioDeleteNote();
	const removeEntry = usePortfolioDeleteEntry();
	const [entering, setEntering] = useState(false);
	const [editingEntry, setEditingEntry] = useState<NoteEntryResponse | null>(null);
	const [editingNote, setEditingNote] = useState(false);
	const [removing, setRemoving] = useState(false);
	const refresh = () =>
		queryClient.invalidateQueries({ queryKey: getPortfolioListNotesQueryKey(book.id) });
	return (
		<li className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
			<div className="flex items-start justify-between gap-3">
				<div className="flex flex-col gap-0.5">
					<h3 className="font-semibold">{note.title}</h3>
					{note.text ? <p className="text-sm text-muted">{note.text}</p> : null}
				</div>
			</div>
			<div className="flex flex-col text-sm">
				<span className="text-xs text-muted">{t.portfolio.spentTotal}</span>
				<b className="text-lg">{formatMoney(note.spent, book.currency)}</b>
			</div>
			{note.entries.length > 0 ? (
				<ol className="flex flex-col gap-1.5 border-s-2 border-border ps-3 text-sm">
					{note.entries
						.filter((entry) => entry.kind !== "value")
						.map((entry) => (
							<li key={entry.id} className="flex items-start justify-between gap-2">
								<span className="flex flex-col">
									<span>
										<b>
											{t.portfolio.kinds[entry.kind as keyof typeof t.portfolio.kinds] ??
												entry.kind}
										</b>
										{entry.amount ? ` · ${formatMoney(entry.amount, book.currency)}` : ""}
									</span>
									<span className="text-xs text-muted">
										{formatFullDate(entry.occurred_on)}
										{entry.memo ? ` — ${entry.memo}` : ""}
									</span>
								</span>
								<span className="flex shrink-0 gap-1">
									<Button
										size="sm"
										variant="ghost"
										aria-label={t.portfolio.editEntry}
										onPress={() => setEditingEntry(entry)}
									>
										{t.portfolio.edit}
									</Button>
									<Button
										size="sm"
										variant="ghost"
										aria-label={t.portfolio.deleteEntry}
										onPress={async () => {
											try {
												await removeEntry.mutateAsync({
													bookId: book.id,
													noteId: note.id,
													entryId: entry.id,
												});
												await refresh();
											} catch (error) {
												reportFailure(error);
											}
										}}
									>
										×
									</Button>
								</span>
							</li>
						))}
				</ol>
			) : null}
			<div className="flex gap-2">
				<Button size="sm" variant="secondary" onPress={() => setEntering(true)}>
					{t.portfolio.addEntry}
				</Button>
				<Button size="sm" variant="ghost" onPress={() => setEditingNote(true)}>
					{t.portfolio.edit}
				</Button>
				<Button size="sm" variant="ghost" onPress={() => setRemoving(true)}>
					{t.common.delete}
				</Button>
			</div>
			<Modal
				isOpen={editingNote}
				onOpenChange={setEditingNote}
				title={t.portfolio.editNote}
				size="sm"
			>
				<NoteForm book={book} note={note} onDone={() => setEditingNote(false)} />
			</Modal>
			<Modal
				isOpen={editingEntry !== null}
				onOpenChange={(open) => !open && setEditingEntry(null)}
				title={t.portfolio.editEntry}
				size="sm"
			>
				{editingEntry ? (
					<EntryForm
						key={editingEntry.id}
						book={book}
						note={note}
						entry={editingEntry}
						onDone={() => setEditingEntry(null)}
					/>
				) : null}
			</Modal>
			<Modal isOpen={entering} onOpenChange={setEntering} title={note.title} size="sm">
				<EntryForm book={book} note={note} onDone={() => setEntering(false)} />
			</Modal>
			<ConfirmDialog
				isOpen={removing}
				onOpenChange={setRemoving}
				title={t.portfolio.deleteNote}
				description={t.portfolio.deleteNoteBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					try {
						await removeNote.mutateAsync({ bookId: book.id, noteId: note.id });
						await refresh();
						toast.success(t.portfolio.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</li>
	);
}

function Notes({ book }: { book: BookResponse }) {
	const { data = [], isLoading } = usePortfolioListNotes(book.id);
	const [adding, setAdding] = useState(false);
	return (
		<SectionCard
			title={t.portfolio.notes}
			description={t.portfolio.notesLead}
			actions={
				<Button size="sm" onPress={() => setAdding(true)}>
					{t.portfolio.addNote}
				</Button>
			}
		>
			{isLoading ? null : data.length === 0 ? (
				<p className="text-sm text-muted">{t.portfolio.noNotes}</p>
			) : (
				<ul className="grid gap-3 lg:grid-cols-2">
					{data.map((note) => (
						<Note key={note.id} book={book} note={note} />
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.portfolio.addNote} size="sm">
				<NoteForm book={book} onDone={() => setAdding(false)} />
			</Modal>
		</SectionCard>
	);
}

export function Portfolio() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	const instruments = usePortfolioInstruments({
		query: { staleTime: 60_000, refetchInterval: 300_000 },
	});
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<PageHeader title={t.portfolio.title} description={t.portfolio.lead} />
			<PersonalOnly book={book}>
				<Holdings book={book} instruments={instruments.data ?? []} />
				<Notes book={book} />
			</PersonalOnly>
		</div>
	);
}
