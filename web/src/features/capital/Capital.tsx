import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
	Button,
	ConfirmDialog,
	Modal,
	ProgressBar,
	SectionCard,
	StatCard,
	StatusChip,
	toast,
} from "@nyxon/nasim";
import {
	getCapitalListFundsQueryKey,
	useCapitalDeleteFund,
	useCapitalListFunds,
	useCapitalOverview,
} from "@/api/generated/capital/capital";
import type { BookResponse, CircleResponse } from "@/api/generated/model";
import { formatAmount, formatMoney } from "@/shared/format";
import { reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { FundForm, FundMoveForm } from "./CapitalForms";

const Figure = ({ children }: { children: string }) => (
	<span className="text-lg sm:text-xl">{children}</span>
);

export function Overview({ book }: { book: BookResponse }) {
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

export function Funds({ book }: { book: BookResponse }) {
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
