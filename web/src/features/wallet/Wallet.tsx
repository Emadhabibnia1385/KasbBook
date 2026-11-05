import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	EmptyState,
	ErrorState,
	FormRoot,
	Modal,
	PageHeader,
	PageSkeleton,
	SectionCard,
	SelectField,
	StatusChip,
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBooksListConversionsQueryKey,
	getBooksListCurrenciesQueryKey,
	getBooksWalletQueryKey,
	useBooksConvert,
	useBooksListConversions,
	useBooksListCurrencies,
	useBooksSetCurrency,
	useBooksWallet,
} from "@/api/generated/books/books";
import type { BookResponse, CurrencyOptionResponse } from "@/api/generated/model";
import { useActiveBook } from "@/features/books/useActiveBook";
import { currencyName, formatDay, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

// Money stays a string from the keyboard to the API: it is only checked here, never parsed into a float.
const amount = z
	.string()
	.transform(toAscii)
	.refine((value) => /^\d+(\.\d{1,4})?$/.test(value) && Number(value) > 0, {
		error: t.wallet.badAmount,
	});

function conversionSchema(baseCode: string | undefined) {
	return z
		.object({
			from: z.string({ error: t.wallet.needCurrency }).min(1, { error: t.wallet.needCurrency }),
			to: z.string({ error: t.wallet.needCurrency }).min(1, { error: t.wallet.needCurrency }),
			fromAmount: amount,
			toAmount: amount,
			baseValue: z.string(),
			note: z.string().max(300),
		})
		.superRefine((value, ctx) => {
			if (value.from && value.from === value.to) {
				ctx.addIssue({ code: "custom", path: ["to"], message: t.wallet.sameCurrency });
			}
			// The server says so rather than guess a rate when neither side is the book's own currency.
			const needsBase = value.from && value.to && value.from !== baseCode && value.to !== baseCode;
			if (needsBase && !amount.safeParse(value.baseValue).success) {
				ctx.addIssue({ code: "custom", path: ["baseValue"], message: t.wallet.badAmount });
			}
		});
}
type Values = z.input<ReturnType<typeof conversionSchema>>;

function ConvertForm({
	book,
	options,
	onDone,
}: {
	book: BookResponse;
	options: CurrencyOptionResponse[];
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const convert = useBooksConvert();
	const held = options.filter((option) => option.enabled);
	const baseCode = options.find((option) => option.is_base)?.code;
	const schema = useMemo(() => conversionSchema(baseCode), [baseCode]);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			from: held[0]?.code ?? "",
			to: held[1]?.code ?? "",
			fromAmount: "",
			toAmount: "",
			baseValue: "",
			note: "",
		},
	});
	const from = useWatch({ control: form.control, name: "from" });
	const to = useWatch({ control: form.control, name: "to" });
	const needsBase = Boolean(from && to && from !== to && from !== baseCode && to !== baseCode);
	const choices = held.map((option) => ({
		value: option.code,
		label: `${option.name} (${option.code})`,
	}));
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					await convert.mutateAsync({
						bookId: book.id,
						data: {
							from_currency: values.from,
							from_amount: values.fromAmount,
							to_currency: values.to,
							to_amount: values.toAmount,
							base_value: needsBase ? values.baseValue : null,
							note: values.note || null,
						},
					});
					await queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(book.id) });
					await queryClient.invalidateQueries({
						queryKey: getBooksListConversionsQueryKey(book.id),
					});
					toast.success(t.wallet.saved);
					onDone();
				} catch (error) {
					toast.danger(error instanceof Error ? error.message : t.errors.unknown);
				}
			}}
		>
			<SelectField name="from" label={t.wallet.from} options={choices} isRequired />
			<TextField
				name="fromAmount"
				label={t.wallet.fromAmount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			<SelectField name="to" label={t.wallet.to} options={choices} isRequired />
			<TextField
				name="toAmount"
				label={t.wallet.toAmount}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{needsBase ? (
				<TextField
					name="baseValue"
					label={`${t.wallet.baseValue} (${currencyName(baseCode ?? book.currency)})`}
					description={t.wallet.baseValueHint}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			) : null}
			<TextField name="note" label={t.wallet.note} />
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

function Balances({ book }: { book: BookResponse }) {
	const { data = [], isLoading, isError, refetch } = useBooksWallet(book.id);
	if (isLoading) return <PageSkeleton header={false} rows={2} />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!data.length) return <EmptyState title={t.wallet.noBalances} />;
	return (
		<ul className="grid gap-3 sm:grid-cols-2">
			{data.map((row) => (
				<li
					key={row.code}
					className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-surface p-4"
				>
					<span className="flex flex-col">
						<span className="font-medium">{row.name}</span>
						{row.is_base ? <span className="text-xs text-muted">{t.wallet.base}</span> : null}
					</span>
					<span className="text-lg font-semibold">{formatMoney(row.amount, row.code)}</span>
				</li>
			))}
		</ul>
	);
}

function Currencies({ book, options }: { book: BookResponse; options: CurrencyOptionResponse[] }) {
	const queryClient = useQueryClient();
	const setCurrency = useBooksSetCurrency();
	return (
		<ul className="flex flex-col gap-2">
			{options.map((option) => (
				<li
					key={option.code}
					className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
				>
					<span className="flex flex-wrap items-center gap-2">
						<span className="font-medium">{option.name}</span>
						<span dir="ltr" className="text-sm text-muted">
							{option.code}
						</span>
						{option.is_base ? <StatusChip tone="info" label={t.wallet.base} /> : null}
						<StatusChip
							tone={option.enabled ? "success" : "neutral"}
							label={option.enabled ? t.wallet.enabled : t.wallet.disabled}
						/>
					</span>
					<Button
						size="sm"
						variant="secondary"
						isDisabled={option.is_base}
						isPending={setCurrency.isPending && setCurrency.variables?.code === option.code}
						onPress={async () => {
							try {
								await setCurrency.mutateAsync({
									bookId: book.id,
									code: option.code,
									data: { enabled: !option.enabled },
								});
								await queryClient.invalidateQueries({
									queryKey: getBooksListCurrenciesQueryKey(book.id),
								});
								await queryClient.invalidateQueries({ queryKey: getBooksWalletQueryKey(book.id) });
								toast.success(t.wallet.switched);
							} catch (error) {
								toast.danger(error instanceof Error ? error.message : t.errors.unknown);
							}
						}}
					>
						{option.enabled ? t.wallet.turnOff : t.wallet.turnOn}
					</Button>
				</li>
			))}
		</ul>
	);
}

function Conversions({ book, options }: { book: BookResponse; options: CurrencyOptionResponse[] }) {
	const [adding, setAdding] = useState(false);
	const { data = [], isLoading, isError, refetch } = useBooksListConversions(book.id);
	const enough = options.filter((option) => option.enabled).length >= 2;
	return (
		<div className="flex flex-col gap-3">
			<p className="text-sm text-muted">{t.wallet.conversionsHint}</p>
			{enough ? (
				<Button className="self-start" onPress={() => setAdding(true)}>
					{t.wallet.convert}
				</Button>
			) : (
				<p className="text-sm text-muted">{t.wallet.needTwo}</p>
			)}
			{isLoading ? (
				<PageSkeleton header={false} rows={2} />
			) : isError ? (
				<ErrorState onRetry={() => void refetch()} />
			) : data.length === 0 ? (
				<EmptyState title={t.wallet.noConversions} />
			) : (
				<ul className="flex flex-col gap-2">
					{data.map((row) => (
						<li key={row.id} className="flex flex-col gap-1 rounded-xl border border-border p-3">
							<span className="font-medium">
								{formatMoney(row.from_amount, row.from_currency)} {t.wallet.arrow}{" "}
								{formatMoney(row.to_amount, row.to_currency)}
							</span>
							<span className="text-sm text-muted">
								{formatDay(row.occurred_on)}
								{row.note ? ` · ${row.note}` : ""}
							</span>
						</li>
					))}
				</ul>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.wallet.convert} size="sm">
				<ConvertForm book={book} options={options} onDone={() => setAdding(false)} />
			</Modal>
		</div>
	);
}

function Content({ book }: { book: BookResponse }) {
	const currencies = useBooksListCurrencies(book.id);
	const options = currencies.data ?? [];
	return (
		<div className="flex flex-col gap-5">
			<PageHeader title={t.wallet.title} description={book.name} />
			<SectionCard title={t.wallet.balances} description={t.wallet.balancesHint}>
				<Balances book={book} />
			</SectionCard>
			<div className="grid gap-5 lg:grid-cols-2">
				<SectionCard title={t.wallet.currencies} description={t.wallet.currenciesHint}>
					{currencies.isLoading ? (
						<PageSkeleton header={false} rows={3} />
					) : currencies.isError ? (
						<ErrorState onRetry={() => void currencies.refetch()} />
					) : (
						<Currencies book={book} options={options} />
					)}
				</SectionCard>
				<SectionCard title={t.wallet.conversions}>
					<Conversions book={book} options={options} />
				</SectionCard>
			</div>
		</div>
	);
}

export function Wallet() {
	const { book, isLoading, isError, refetch } = useActiveBook();
	if (isLoading) return <PageSkeleton />;
	if (isError) return <ErrorState onRetry={() => void refetch()} />;
	if (!book)
		return <EmptyState as="h1" title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />;
	return <Content book={book} />;
}
