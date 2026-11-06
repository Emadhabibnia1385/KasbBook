import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
	Button,
	EmptyState,
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
	getBooksListBooksQueryKey,
	useBooksCreateBook,
	useBooksWallet,
} from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { currencyName, formatMoney } from "@/shared/format";
import { t } from "@/strings";
import { Categories } from "./Categories";
import { CurrencyPicker } from "@/features/currencies/CurrencyPicker";
import { selectBook, useActiveBook } from "./useActiveBook";

const TYPES = [
	{ value: "personal", label: t.book.personal },
	{ value: "business", label: t.book.business },
	{ value: "team", label: t.book.team },
	{ value: "organization", label: t.book.organization },
];

const schema = z.object({
	name: z.string().trim().min(1, { error: t.books.needName }).max(120),
	type: z.string({ error: t.books.needType }),
});
type Values = z.input<typeof schema>;

function Wallet({ book }: { book: BookResponse }) {
	const { data = [] } = useBooksWallet(book.id);
	if (!data.length) return null;
	return (
		<ul className="flex flex-wrap gap-2 text-sm text-muted">
			{data.map((row) => (
				<li key={row.code}>{formatMoney(row.amount, row.code)}</li>
			))}
		</ul>
	);
}

export function Books({ presetCurrency }: { presetCurrency?: string | undefined }) {
	const queryClient = useQueryClient();
	const { books, book: active, isLoading } = useActiveBook();
	// Arriving from a refused base-currency change opens the form with that unit already chosen.
	const [adding, setAdding] = useState(Boolean(presetCurrency));
	const [currency, setCurrency] = useState(presetCurrency ?? "IRT");
	const [pickingCurrency, setPickingCurrency] = useState(false);
	const create = useBooksCreateBook();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { name: "", type: "business" },
	});
	if (isLoading) return <PageSkeleton />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.nav.books}
				actions={<Button onPress={() => setAdding(true)}>{t.books.add}</Button>}
			/>
			{books.length === 0 ? (
				<EmptyState title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />
			) : (
				<div className="grid gap-4 md:grid-cols-2">
					{books.map((book) => (
						<SectionCard
							key={book.id}
							title={book.name}
							actions={
								book.id === active?.id ? (
									<StatusChip tone="success" label={t.books.active} />
								) : (
									<Button size="sm" variant="secondary" onPress={() => selectBook(book.id)}>
										{t.books.use}
									</Button>
								)
							}
						>
							<p className="text-sm text-muted">
								{TYPES.find((type) => type.value === book.type)?.label ?? book.type} ·{" "}
								{currencyName(book.currency)}
							</p>
							<Wallet book={book} />
						</SectionCard>
					))}
				</div>
			)}
			{active ? (
				<Categories book={active} />
			) : (
				<p className="text-sm text-muted">{t.scope.needsBook}</p>
			)}
			<Modal isOpen={adding} onOpenChange={setAdding} title={t.books.add} size="sm">
				<FormRoot
					form={form}
					className="flex flex-col gap-4"
					onSubmit={async (values) => {
						try {
							const made = await create.mutateAsync({
								data: { name: values.name, type: values.type, currency },
							});
							await queryClient.invalidateQueries({ queryKey: getBooksListBooksQueryKey() });
							selectBook(made.id);
							toast.success(t.books.created);
							form.reset();
							setAdding(false);
						} catch (error) {
							toast.danger(error instanceof Error ? error.message : t.errors.unknown);
						}
					}}
				>
					<TextField name="name" label={t.books.name} isRequired />
					<SelectField name="type" label={t.books.type} options={TYPES} />
					<div className="flex flex-col gap-1">
						<span className="text-sm font-medium">{t.currencies.createUnit}</span>
						<Button
							variant="outline"
							className="justify-between"
							onPress={() => setPickingCurrency(true)}
						>
							<span>{currencyName(currency)}</span>
							<span dir="ltr" className="text-sm text-muted">
								{currency}
							</span>
						</Button>
					</div>
					<SubmitButton>{t.common.save}</SubmitButton>
				</FormRoot>
			</Modal>
			<CurrencyPicker
				isOpen={pickingCurrency}
				onOpenChange={setPickingCurrency}
				title={t.currencies.pickUnit}
				current={currency}
				onPick={setCurrency}
			/>
		</div>
	);
}
