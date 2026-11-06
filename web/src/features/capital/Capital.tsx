import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
	Button,
	ConfirmDialog,
	ErrorState,
	Modal,
	PageHeader,
	PageSkeleton,
	ProgressBar,
	SectionCard,
	StatCard,
	StatusChip,
	toast,
} from "@nyxon/nasim";
import {
	getCapitalListAssetsQueryKey,
	getCapitalListFundsQueryKey,
	getCapitalOverviewQueryKey,
	useCapitalDeleteAsset,
	useCapitalDeleteFund,
	useCapitalListAssets,
	useCapitalListFunds,
	useCapitalOverview,
} from "@/api/generated/capital/capital";
import type { AssetResponse, BookResponse, CircleResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { PersonalOnly } from "@/features/manage/PersonalOnly";
import { BookRequired } from "@/features/books/BookRequired";
import { ManageTabs } from "@/features/manage/ManageTabs";
import { formatAmount, formatFullDate, formatMoney } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { BuyAssetForm, FundForm, FundMoveForm, SellAssetForm } from "./CapitalForms";

const Figure = ({ children }: { children: string }) => (
	<span className="text-lg sm:text-xl">{children}</span>
);

function Overview({ book }: { book: BookResponse }) {
	const { data } = useCapitalOverview(book.id);
	if (!data) return null;
	return (
		<div className="flex flex-col gap-2">
			<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard
					label={t.capital.overviewAssets}
					value={<Figure>{formatMoney(data.assets, book.currency)}</Figure>}
				/>
				<StatCard
					label={t.capital.overviewClaims}
					value={<Figure>{formatMoney(data.fund_claims, book.currency)}</Figure>}
				/>
				<StatCard
					label={t.capital.overviewDebts}
					value={<Figure>{formatMoney(data.liabilities, book.currency)}</Figure>}
				/>
				<StatCard
					label={t.capital.overviewNet}
					value={<Figure>{formatMoney(data.net, book.currency)}</Figure>}
				/>
			</div>
			<p className="text-xs text-muted">{t.capital.overviewNote}</p>
		</div>
	);
}

function Assets({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = useCapitalListAssets(book.id);
	const remove = useCapitalDeleteAsset();
	const [buying, setBuying] = useState(false);
	const [selling, setSelling] = useState<AssetResponse | null>(null);
	const [removing, setRemoving] = useState<AssetResponse | null>(null);
	return (
		<SectionCard
			title={t.capital.assets}
			description={t.capital.assetsHint}
			actions={
				<Button size="sm" onPress={() => setBuying(true)}>
					{t.capital.buy}
				</Button>
			}
		>
			{isLoading ? null : data.length === 0 ? (
				<p className="text-sm text-muted">{t.capital.noAssets}</p>
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((asset) => {
						const sold = asset.sold_on !== null && asset.sold_on !== undefined;
						return (
							<li
								key={asset.id}
								className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-3"
							>
								<div className="flex items-center justify-between gap-2">
									<span className="font-medium">{asset.name}</span>
									<span className="flex items-center gap-2">
										<StatusChip
											tone="neutral"
											label={
												t.capital.kinds[asset.kind as keyof typeof t.capital.kinds] ?? asset.kind
											}
										/>
										{asset.loan_id ? <StatusChip tone="info" label={t.capital.viaLoan} /> : null}
									</span>
								</div>
								<p className="text-lg font-semibold">{formatMoney(asset.cost, book.currency)}</p>
								<p className="text-sm text-muted">
									{t.capital.boughtOn} {formatFullDate(asset.acquired_on)}
									{asset.quantity
										? ` · ${formatAmount(Number(asset.quantity))} ${asset.unit ?? ""}`
										: ""}
								</p>
								{sold && asset.sold_on ? (
									<p className="text-sm text-success">
										{t.capital.sold} {formatFullDate(asset.sold_on)} · {t.capital.soldFor}{" "}
										{formatMoney(asset.sold_for ?? "0", book.currency)}
									</p>
								) : null}
								<div className="flex flex-wrap gap-2">
									{sold ? null : (
										<Button size="sm" variant="secondary" onPress={() => setSelling(asset)}>
											{t.capital.sell}
										</Button>
									)}
									{asset.loan_id ? (
										<Link to="/planning" className="self-center text-sm text-accent">
											{t.planning.loans}
										</Link>
									) : null}
									{sold ? null : (
										<Button size="sm" variant="ghost" onPress={() => setRemoving(asset)}>
											{t.common.delete}
										</Button>
									)}
								</div>
							</li>
						);
					})}
				</ul>
			)}
			<Modal isOpen={buying} onOpenChange={setBuying} title={t.capital.buy} size="md">
				<BuyAssetForm book={book} onDone={() => setBuying(false)} />
			</Modal>
			<Modal
				isOpen={selling !== null}
				onOpenChange={(open) => !open && setSelling(null)}
				title={selling ? `${t.capital.sellTitle} ${selling.name}` : t.capital.sell}
				size="sm"
			>
				{selling ? (
					<SellAssetForm
						key={selling.id}
						book={book}
						asset={selling}
						onDone={() => setSelling(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.capital.deleteAsset}
				description={t.capital.deleteAssetBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, assetId: removing.id });
						await Promise.all([
							queryClient.invalidateQueries({ queryKey: getCapitalListAssetsQueryKey(book.id) }),
							queryClient.invalidateQueries({ queryKey: getCapitalOverviewQueryKey(book.id) }),
							refreshMoney(queryClient, book.id),
						]);
						toast.success(t.capital.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}

function Funds({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const { data = [], isLoading } = useCapitalListFunds(book.id);
	const remove = useCapitalDeleteFund();
	const [adding, setAdding] = useState(false);
	const [moving, setMoving] = useState<{ fund: CircleResponse; mode: "pay" | "receive" } | null>(
		null,
	);
	const [removing, setRemoving] = useState<CircleResponse | null>(null);
	return (
		<SectionCard
			title={t.capital.funds}
			description={t.capital.fundsHint}
			actions={
				<Button size="sm" onPress={() => setAdding(true)}>
					{t.capital.addFund}
				</Button>
			}
		>
			{isLoading ? null : data.length === 0 ? (
				<p className="text-sm text-muted">{t.capital.noFunds}</p>
			) : (
				<ul className="grid gap-3 md:grid-cols-2">
					{data.map((fund) => {
						const received = fund.received_on !== null && fund.received_on !== undefined;
						const done = fund.paid_months >= fund.months;
						return (
							<li
								key={fund.id}
								className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-3"
							>
								<div className="flex items-center justify-between gap-2">
									<span className="font-medium">{fund.name}</span>
									{received ? <StatusChip tone="success" label={t.capital.received} /> : null}
								</div>
								<ProgressBar
									aria-label={fund.name}
									value={Math.min(100, (fund.paid_months / fund.months) * 100)}
									className="w-full"
								>
									<ProgressBar.Track>
										<ProgressBar.Fill />
									</ProgressBar.Track>
								</ProgressBar>
								<p className="text-sm text-muted">
									{t.capital.paidMonths} {formatAmount(fund.paid_months)} /{" "}
									{formatAmount(fund.months)} · {formatMoney(fund.monthly_amount, book.currency)}
									{fund.turn_month
										? ` · ${t.capital.turnMonth} ${formatAmount(fund.turn_month)}`
										: ""}
								</p>
								<p className="text-sm text-muted">
									{t.capital.payout}: {formatMoney(fund.payout_amount, book.currency)}
								</p>
								{Number(fund.claim) > 0 ? (
									<p className="text-sm">
										{t.capital.claim}: <b>{formatMoney(fund.claim, book.currency)}</b>
									</p>
								) : null}
								{Number(fund.owed) > 0 ? (
									<p className="text-sm">
										{t.capital.owed}: <b>{formatMoney(fund.owed, book.currency)}</b>
									</p>
								) : null}
								<div className="flex flex-wrap gap-2">
									{done ? null : (
										<Button
											size="sm"
											variant="secondary"
											onPress={() => setMoving({ fund, mode: "pay" })}
										>
											{t.capital.payMonth}
										</Button>
									)}
									{received ? null : (
										<Button
											size="sm"
											variant="secondary"
											onPress={() => setMoving({ fund, mode: "receive" })}
										>
											{t.capital.receive}
										</Button>
									)}
									{fund.paid_months === 0 && !received ? (
										<Button size="sm" variant="ghost" onPress={() => setRemoving(fund)}>
											{t.common.delete}
										</Button>
									) : null}
								</div>
							</li>
						);
					})}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.capital.addFund} size="sm">
				<FundForm book={book} onDone={() => setAdding(false)} />
			</Modal>
			<Modal
				isOpen={moving !== null}
				onOpenChange={(open) => !open && setMoving(null)}
				title={
					moving
						? `${moving.mode === "pay" ? t.capital.payTitle : t.capital.receiveTitle} · ${moving.fund.name}`
						: ""
				}
				size="sm"
			>
				{moving ? (
					<FundMoveForm
						key={`${moving.fund.id}-${moving.mode}`}
						book={book}
						fund={moving.fund}
						mode={moving.mode}
						onDone={() => setMoving(null)}
					/>
				) : null}
			</Modal>
			<ConfirmDialog
				isOpen={removing !== null}
				onOpenChange={(open) => !open && setRemoving(null)}
				title={t.capital.deleteFund}
				description={t.capital.deleteFundBody}
				confirmLabel={t.common.delete}
				tone="danger"
				onConfirm={async () => {
					if (!removing) return;
					try {
						await remove.mutateAsync({ bookId: book.id, fundId: removing.id });
						await queryClient.invalidateQueries({ queryKey: getCapitalListFundsQueryKey(book.id) });
						toast.success(t.capital.deleted);
					} catch (error) {
						reportFailure(error);
						throw error;
					}
				}}
			/>
		</SectionCard>
	);
}

export function Capital() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book) return <BookRequired />;
	return (
		<div className="flex flex-col gap-5">
			<ManageTabs />
			<PageHeader title={t.capital.title} description={t.capital.lead} />
			<PersonalOnly book={book}>
				<Overview book={book} />
				<Assets book={book} />
				<Funds book={book} />
			</PersonalOnly>
		</div>
	);
}
