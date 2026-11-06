import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button, Notice, SectionCard, StatusChip, toast } from "@nyxon/nasim";
import {
	getBooksGetBookQueryKey,
	getBooksListBooksQueryKey,
	getBooksListCurrenciesQueryKey,
	getBooksWalletQueryKey,
	useBooksSetBaseCurrency,
	useBooksSetCurrency,
} from "@/api/generated/books/books";
import type { BookResponse, CurrencyOptionResponse } from "@/api/generated/model";
import { currencyName } from "@/shared/format";
import { t } from "@/strings";
import { CurrencyPicker } from "./CurrencyPicker";

// The book's currencies in two parts: the main unit everything is kept in, and the short list of
// others it may also hold. The catalog is long, so it lives behind a picker instead of on the page.
export function CurrencyMenu({
	book,
	options,
}: {
	book: BookResponse;
	options: CurrencyOptionResponse[];
}) {
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const setCurrency = useBooksSetCurrency();
	const setBase = useBooksSetBaseCurrency();
	const [picking, setPicking] = useState<"add" | "base" | null>(null);
	// The server's refusal for a book with history, kept on screen with the way forward.
	const [refusal, setRefusal] = useState<{ message: string; code: string } | null>(null);

	const refresh = async () => {
		await queryClient.invalidateQueries({ queryKey: getBooksListCurrenciesQueryKey(book.id) });
		await queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(book.id) });
	};

	const toggle = async (code: string, enabled: boolean) => {
		try {
			await setCurrency.mutateAsync({ bookId: book.id, code, data: { enabled } });
			await refresh();
			toast.success(t.wallet.switched);
		} catch (error) {
			toast.danger(error instanceof Error ? error.message : t.errors.unknown);
		}
	};

	const changeBase = async (code: string) => {
		setRefusal(null);
		try {
			await setBase.mutateAsync({ bookId: book.id, data: { code } });
			await queryClient.invalidateQueries({ queryKey: getBooksListBooksQueryKey() });
			await queryClient.invalidateQueries({ queryKey: getBooksGetBookQueryKey(book.id) });
			await refresh();
			toast.success(t.currencies.baseChanged);
		} catch (error) {
			setRefusal({ message: error instanceof Error ? error.message : t.errors.unknown, code });
		}
	};

	const enabled = options.filter((option) => option.enabled && !option.is_base);
	// What cannot be picked to add: already ticked, or the base itself.
	const taken = Object.fromEntries(
		options
			.filter((option) => option.enabled)
			.map((option) => [option.code, option.is_base ? t.currencies.baseReason : t.wallet.enabled]),
	);

	return (
		<>
			<SectionCard title={t.wallet.currencies} description={t.wallet.currenciesHint}>
				<div className="flex flex-col gap-4">
					<div className="flex flex-col gap-2 rounded-xl border border-border p-3">
						<div className="flex flex-wrap items-center justify-between gap-3">
							<span className="flex flex-col">
								<span className="text-xs text-muted">{t.currencies.baseTitle}</span>
								<span className="flex items-center gap-2 text-lg font-semibold">
									{currencyName(book.currency)}
									<span dir="ltr" className="text-sm font-normal text-muted">
										{book.currency}
									</span>
								</span>
							</span>
							<Button
								size="sm"
								variant="secondary"
								isPending={setBase.isPending}
								onPress={() => setPicking("base")}
							>
								{t.currencies.changeBase}
							</Button>
						</div>
						<p className="text-xs text-muted">{t.currencies.baseHint}</p>
						{refusal ? (
							<div className="flex flex-col gap-2">
								<Notice tone="warning" role="alert">
									{refusal.message}
								</Notice>
								<Button
									variant="outline"
									className="self-start"
									onPress={() => void navigate({ to: "/books", search: { new: refusal.code } })}
								>
									{t.currencies.newBookWith}
								</Button>
							</div>
						) : null}
					</div>
					<div className="flex flex-col gap-2">
						<div className="flex items-center justify-between gap-3">
							<span className="text-sm font-medium">{t.currencies.otherUnits}</span>
							<Button size="sm" onPress={() => setPicking("add")}>
								{t.currencies.add}
							</Button>
						</div>
						{enabled.length === 0 ? (
							<p className="text-sm text-muted">{t.currencies.noneActive}</p>
						) : (
							<ul className="flex flex-col gap-2">
								{enabled.map((option) => (
									<li
										key={option.code}
										className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
									>
										<span className="flex min-w-0 flex-wrap items-center gap-2">
											<span className="font-medium">{option.name}</span>
											<span dir="ltr" className="text-sm text-muted">
												{option.code}
											</span>
											<StatusChip tone="success" label={t.wallet.enabled} />
										</span>
										<Button
											size="sm"
											variant="ghost"
											isPending={
												setCurrency.isPending && setCurrency.variables?.code === option.code
											}
											onPress={() => void toggle(option.code, false)}
										>
											{t.wallet.turnOff}
										</Button>
									</li>
								))}
							</ul>
						)}
					</div>
				</div>
			</SectionCard>
			<CurrencyPicker
				isOpen={picking === "add"}
				onOpenChange={(open) => !open && setPicking(null)}
				title={t.currencies.addTitle}
				disabled={taken}
				onPick={(code) => void toggle(code, true)}
			/>
			<CurrencyPicker
				isOpen={picking === "base"}
				onOpenChange={(open) => !open && setPicking(null)}
				title={t.currencies.pickUnit}
				current={book.currency}
				onPick={(code) => void changeBase(code)}
			/>
		</>
	);
}
