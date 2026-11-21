import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
	Button,
	ConfirmDialog,
	EmptyState,
	ErrorState,
	PageHeader,
	PageSkeleton,
	SectionCard,
	toast,
} from "@nyxon/nasim";
import {
	getBanksListMineQueryKey,
	useBanksDelete,
	useBanksListForBook,
	useBanksAssign,
	useBanksListMine,
	useBanksLink,
	useBanksReconcile,
	useBanksUnlink,
	useBanksUpdate,
	useBanksUpdateLink,
} from "@/api/generated/banks/banks";
import type { BankAccountResponse, BookResponse } from "@/api/generated/model";
import { BookRequired } from "@/features/books/BookRequired";
import { useActiveBook } from "@/features/books/useActiveBook";
import { PlusIcon } from "@/shared/icons";
import { formatAmount, formatMoney } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { BankBalances, BankShareDonut, BankSplitPanel } from "./BankBalances";
import { BankDialog } from "./BankForm";
import { Transfers } from "./Transfers";

/** 6037 9972 5500 8764: a card number is read in fours. */
function grouped(card: string): string {
	return card.replace(/(\d{4})(?=\d)/g, "$1 ");
}

function Copyable({ label, value }: { label: string; value: string }) {
	return (
		<button
			type="button"
			title={t.banks.copy}
			className="flex items-baseline gap-2 text-start text-sm hover:underline"
			onClick={() => {
				void navigator.clipboard?.writeText(value.replace(/\s/g, ""));
				toast.success(t.banks.copied);
			}}
		>
			<span className="text-muted">{label}</span>
			<bdi dir="ltr" className="tabular-nums">
				{value}
			</bdi>
		</button>
	);
}

/** The one real balance, worked out two independent ways: the journal and the transactions. They must agree. */
function Check({ bank }: { bank: BankAccountResponse }) {
	const { data } = useBanksReconcile(bank.id);
	if (!data) return null;
	return (
		<p className={data.consistent ? "text-xs text-success" : "text-xs text-danger"}>
			{data.consistent ? t.banks.checkOk : t.banks.checkBad}
		</p>
	);
}

function BankCard({
	bank,
	book,
	onEdit,
}: {
	bank: BankAccountResponse;
	book: BookResponse;
	onEdit: () => void;
}) {
	const queryClient = useQueryClient();
	const update = useBanksUpdate();
	const updateLink = useBanksUpdateLink();
	const link = useBanksLink();
	const unlink = useBanksUnlink();
	const remove = useBanksDelete();
	const assign = useBanksAssign();
	const [removing, setRemoving] = useState(false);
	const [assigning, setAssigning] = useState(false);
	const here = bank.shares.find((share) => share.book_id === book.id);
	const others = bank.shares.filter((share) => share.book_id !== book.id);
	const refresh = () =>
		Promise.all([
			queryClient.invalidateQueries({ queryKey: getBanksListMineQueryKey() }),
			refreshMoney(queryClient, book.id),
		]);
	const run = async (action: () => Promise<unknown>, message: string) => {
		try {
			await action();
			await refresh();
			toast.success(message);
		} catch (error) {
			reportFailure(error);
		}
	};
	return (
		<article className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-4">
			<header className="flex flex-wrap items-start justify-between gap-3">
				<div className="flex min-w-0 flex-col gap-0.5">
					<h3 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
						<bdi>{bank.title}</bdi>
						{here?.is_default ? (
							<span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-soft-foreground">
								{t.banks.defaultMark}
							</span>
						) : null}
						{bank.is_active ? null : (
							<span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs text-muted">
								{t.banks.inactiveMark}
							</span>
						)}
					</h3>
					{bank.display_name ? (
						<span className="text-sm text-muted">
							<bdi>
								{bank.bank_name} · {bank.holder_name}
							</bdi>
						</span>
					) : null}
				</div>
				<div className="flex flex-col items-end">
					<span className="text-xs text-muted">{t.banks.total}</span>
					<span className="text-xl font-semibold tabular-nums">
						{formatMoney(bank.total_balance, bank.currency)}
					</span>
				</div>
			</header>
			<div className="flex flex-col gap-1">
				{bank.card_number ? (
					<Copyable label={t.banks.card} value={grouped(bank.card_number)} />
				) : null}
				{bank.account_number ? (
					<Copyable label={t.banks.accountNumber} value={bank.account_number} />
				) : null}
				{bank.sheba ? <Copyable label={t.banks.sheba} value={bank.sheba} /> : null}
			</div>
			<div className="grid gap-4 md:grid-cols-2">
				<BankShareDonut bank={bank} currency={bank.currency} highlightBookId={book.id} />
				<div className="flex flex-col gap-2 text-sm">
					<span className="font-medium">{t.banks.perBook}</span>
					<ul className="flex flex-col gap-1.5">
						{bank.shares.map((share) => (
							<li key={share.book_id} className="flex items-center justify-between gap-3">
								<bdi className="truncate">
									{share.book_name}
									{share.book_id === book.id ? ` (${t.banks.thisBook})` : ""}
									{share.is_active ? "" : ` · ${t.banks.inactiveMark}`}
								</bdi>
								<span className="tabular-nums">{formatMoney(share.balance, bank.currency)}</span>
							</li>
						))}
						{Number(bank.opening_balance) !== 0 ? (
							<li className="flex items-center justify-between gap-3 text-muted">
								<span>{t.banks.openingLine}</span>
								<span className="tabular-nums">
									{formatMoney(bank.opening_balance, bank.currency)}
								</span>
							</li>
						) : null}
					</ul>
					{others.length > 0 && here ? (
						<p className="text-xs text-muted">
							{t.banks.thisBook}: {formatMoney(here.balance, bank.currency)} · {t.banks.otherBooks}:{" "}
							{formatMoney(
								others.reduce((sum, share) => sum + Number(share.balance), 0).toFixed(4),
								bank.currency,
							)}
						</p>
					) : null}
					<Check bank={bank} />
				</div>
			</div>
			<footer className="flex flex-wrap gap-2">
				<Button size="sm" variant="secondary" onPress={onEdit}>
					{t.banks.edit}
				</Button>
				{here ? (
					<>
						{here.is_default || !here.is_active || !bank.is_active ? null : (
							<Button
								size="sm"
								variant="secondary"
								onPress={() =>
									run(
										() =>
											updateLink.mutateAsync({
												bookId: book.id,
												bankId: bank.id,
												data: { is_default: true },
											}),
										t.banks.updated,
									)
								}
							>
								{t.banks.makeDefault}
							</Button>
						)}
						<Button
							size="sm"
							variant="secondary"
							onPress={() =>
								run(
									() =>
										updateLink.mutateAsync({
											bookId: book.id,
											bankId: bank.id,
											data: { is_active: !here.is_active },
										}),
									t.banks.updated,
								)
							}
						>
							{here.is_active ? t.banks.switchOffHere : t.banks.switchOnHere}
						</Button>
						<Button
							size="sm"
							variant="secondary"
							onPress={() =>
								run(
									() => unlink.mutateAsync({ bookId: book.id, bankId: bank.id }),
									t.banks.unlinked,
								)
							}
						>
							{t.banks.unlink}
						</Button>
					</>
				) : bank.currency === book.currency ? (
					<Button
						size="sm"
						onPress={() =>
							run(
								() =>
									link.mutateAsync({
										bookId: book.id,
										bankId: bank.id,
										data: { make_default: false },
									}),
								t.banks.linked,
							)
						}
					>
						{t.banks.linkHere}
					</Button>
				) : null}
				<Button
					size="sm"
					variant="secondary"
					onPress={() =>
						run(
							() => update.mutateAsync({ bankId: bank.id, data: { is_active: !bank.is_active } }),
							t.banks.updated,
						)
					}
				>
					{bank.is_active ? t.banks.switchOffAll : t.banks.switchOnAll}
				</Button>
				{here?.is_active && bank.is_active ? (
					<Button size="sm" variant="secondary" onPress={() => setAssigning(true)}>
						{t.banks.assign}
					</Button>
				) : null}
				<Button size="sm" variant="danger-soft" onPress={() => setRemoving(true)}>
					{t.banks.remove}
				</Button>
			</footer>
			<ConfirmDialog
				isOpen={assigning}
				onOpenChange={setAssigning}
				title={t.banks.assignTitle}
				description={t.banks.assignBody}
				confirmLabel={t.banks.assignConfirm}
				onConfirm={async () => {
					try {
						const result = await assign.mutateAsync({
							bookId: book.id,
							bankId: bank.id,
							data: {},
						});
						await refresh();
						toast.success(
							result.moved === 0
								? t.banks.assignNone
								: `${formatAmount(result.moved)} ${t.banks.assignDone}${result.left ? ` — ${formatAmount(result.left)} ${t.banks.assignLeft}` : ""}`,
						);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
			<ConfirmDialog
				isOpen={removing}
				onOpenChange={setRemoving}
				title={t.banks.removeTitle}
				description={t.banks.removeBody}
				confirmLabel={t.banks.remove}
				tone="danger"
				onConfirm={async () => {
					try {
						await remove.mutateAsync({ bankId: bank.id });
						await refresh();
						toast.success(t.banks.removed);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</article>
	);
}

function Mine({ book, books }: { book: BookResponse; books: BookResponse[] }) {
	const query = useBanksListMine();
	const [editing, setEditing] = useState<BankAccountResponse | null>(null);
	const [adding, setAdding] = useState(false);
	if (query.isLoading) return <PageSkeleton header={false} rows={2} />;
	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
	const banks = query.data ?? [];
	return (
		<>
			{banks.length === 0 ? (
				<EmptyState
					title={t.banks.empty}
					description={t.banks.emptyHint}
					action={
						<Button onPress={() => setAdding(true)}>
							<PlusIcon aria-hidden className="size-4" />
							{t.banks.add}
						</Button>
					}
				/>
			) : (
				<div className="flex flex-col gap-4">
					{banks.map((bank) => (
						<BankCard key={bank.id} bank={bank} book={book} onEdit={() => setEditing(bank)} />
					))}
					<div>
						<Button variant="secondary" onPress={() => setAdding(true)}>
							<PlusIcon aria-hidden className="size-4" />
							{t.banks.add}
						</Button>
					</div>
				</div>
			)}
			<BankDialog
				isOpen={adding}
				onOpenChange={setAdding}
				bank={null}
				books={books}
				current={book}
			/>
			<BankDialog
				isOpen={editing !== null}
				onOpenChange={(open) => !open && setEditing(null)}
				bank={editing}
				books={books}
				current={book}
			/>
		</>
	);
}

/** Accounts others own but this book uses (a colleague's card in a team book): what you may see of them. */
function SharedWithMe({ book }: { book: BookResponse }) {
	const query = useBanksListForBook(book.id);
	const theirs = (query.data ?? []).filter((row) => !row.is_owner);
	if (theirs.length === 0) return null;
	return (
		<SectionCard title={t.banks.otherBooks} description={t.banks.manageHint}>
			<ul className="flex flex-col gap-2">
				{theirs.map((row) => (
					<li key={row.id} className="flex items-center justify-between gap-3 text-sm">
						<bdi className="truncate">
							{row.title} {row.card_last4}
						</bdi>
						<span className="tabular-nums">
							{row.balance ? formatMoney(row.balance, row.currency) : ""}
						</span>
					</li>
				))}
			</ul>
		</SectionCard>
	);
}

function Content({ book, books }: { book: BookResponse; books: BookResponse[] }) {
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.banks.title} description={`${book.name} — ${t.banks.lead}`} />
			<BankBalances book={book} />
			<BankSplitPanel book={book} />
			<Transfers book={book} />
			<SectionCard title={t.banks.title}>
				<Mine book={book} books={books} />
			</SectionCard>
			<SharedWithMe book={book} />
		</div>
	);
}

export function Banks() {
	const { book, books, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	return <Content book={book} books={books} />;
}
