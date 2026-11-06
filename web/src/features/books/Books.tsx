import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
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
	SubmitButton,
	TextField,
	toast,
} from "@nyxon/nasim";
import { useAuthMe } from "@/api/generated/auth/auth";
import {
	getBooksListBooksQueryKey,
	useBooksCreateBook,
	useBooksSetCalendar,
} from "@/api/generated/books/books";
import type { BookResponse } from "@/api/generated/model";
import { currencyName } from "@/shared/format";
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

// What each kind of book is for, said under the choice so nobody has to guess.
const TYPE_HINTS: Record<string, string> = {
	personal: t.books.personalHint,
	business: t.books.businessHint,
	team: t.books.teamHint,
	organization: t.books.organizationHint,
};

const schema = z.object({
	name: z.string().trim().min(1, { error: t.books.needName }).max(120),
	type: z.string({ error: t.books.needType }),
});
type Values = z.input<typeof schema>;

const CALENDARS = [
	{ value: "jalali", label: t.books.calendarJalali },
	{ value: "gregorian", label: t.books.calendarGregorian },
];

/** The calendar this book counts its months by, with a way to change it: the recorded days do not move. */
function CalendarSwitch({ book }: { book: BookResponse }) {
	const queryClient = useQueryClient();
	const set = useBooksSetCalendar();
	const current = book.calendar === "gregorian" ? "gregorian" : "jalali";
	return (
		<div className="flex flex-col gap-1.5">
			<div className="flex items-center gap-2">
				<span className="text-sm text-muted">{t.books.calendar}</span>
				{CALENDARS.map((option) => (
					<Button
						key={option.value}
						size="sm"
						variant={option.value === current ? "primary" : "ghost"}
						isDisabled={set.isPending}
						onPress={async () => {
							if (option.value === current) return;
							try {
								await set.mutateAsync({ bookId: book.id, data: { calendar: option.value } });
								await queryClient.invalidateQueries();
								toast.success(t.books.calendarChanged);
							} catch (error) {
								toast.danger(error instanceof Error ? error.message : t.errors.unknown);
							}
						}}
					>
						{option.label}
					</Button>
				))}
			</div>
		</div>
	);
}

export function Books({ presetCurrency }: { presetCurrency?: string | undefined }) {
	const queryClient = useQueryClient();
	const { books, book: active, isLoading } = useActiveBook();
	// Arriving from a refused base-currency change opens the form with that unit already chosen.
	// Arriving with a base currency in the address (the switcher's «افزودن دفتر», a refused currency change)
	// opens the form with that unit already chosen.
	const [adding, setAdding] = useState(false);
	const navigate = useNavigate();
	const formOpen = adding || Boolean(presetCurrency);
	const setAddingOpen = (open: boolean) => {
		setAdding(open);
		if (!open && presetCurrency) void navigate({ to: "/books", search: {}, replace: true });
	};
	// The money and the calendar start from where this account's time zone says the person is; they may change both.
	const me = useAuthMe().data;
	const [chosenCurrency, setCurrency] = useState<string | null>(presetCurrency ?? null);
	const [chosenCalendar, setCalendar] = useState<string | null>(null);
	const currency = chosenCurrency ?? me?.suggested_currency ?? "IRT";
	const calendar = chosenCalendar ?? me?.suggested_calendar ?? "jalali";
	const [pickingCurrency, setPickingCurrency] = useState(false);
	const create = useBooksCreateBook();
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: { name: "", type: "business" },
	});
	const chosenType = useWatch({ control: form.control, name: "type" });
	if (isLoading) return <PageSkeleton />;
	return (
		<div className="flex flex-col gap-5">
			<PageHeader
				title={t.manage.books}
				actions={<Button onPress={() => setAddingOpen(true)}>{t.books.add}</Button>}
			/>
			{books.length === 0 ? (
				<EmptyState title={t.dashboard.noBookTitle} description={t.dashboard.noBook} />
			) : active ? (
				<SectionCard title={active.name}>
					<p className="text-sm text-muted">
						{TYPES.find((type) => type.value === active.type)?.label ?? active.type} ·{" "}
						{currencyName(active.currency)}
					</p>
					<CalendarSwitch book={active} />
				</SectionCard>
			) : null}
			{active ? (
				<Categories book={active} />
			) : (
				<p className="text-sm text-muted">{t.scope.needsBook}</p>
			)}
			<Modal isOpen={formOpen} onOpenChange={setAddingOpen} title={t.books.add} size="sm">
				<FormRoot
					form={form}
					className="flex flex-col gap-4"
					onSubmit={async (values) => {
						try {
							const made = await create.mutateAsync({
								data: { name: values.name, type: values.type, currency, calendar },
							});
							await queryClient.invalidateQueries({ queryKey: getBooksListBooksQueryKey() });
							selectBook(made.id);
							toast.success(t.books.created);
							form.reset();
							setCurrency(null);
							setCalendar(null);
							setAddingOpen(false);
						} catch (error) {
							toast.danger(error instanceof Error ? error.message : t.errors.unknown);
						}
					}}
				>
					<TextField name="name" label={t.books.name} isRequired />
					<div className="flex flex-col gap-1.5">
						<SelectField name="type" label={t.books.type} options={TYPES} />
						<p className="text-sm text-muted">{TYPE_HINTS[chosenType ?? ""] ?? ""}</p>
					</div>
					<div className="flex flex-col gap-1.5">
						<span className="text-sm font-medium">{t.books.baseCurrency}</span>
						<Button
							variant="outline"
							className="w-full justify-between"
							onPress={() => setPickingCurrency(true)}
						>
							<span>{currencyName(currency)}</span>
							<span dir="ltr" className="text-sm text-muted">
								{currency}
							</span>
						</Button>
						<p className="text-sm text-muted">{t.books.baseCurrencyHint}</p>
					</div>
					<div className="flex flex-col gap-1.5">
						<SelectField
							label={t.books.calendar}
							options={CALENDARS}
							value={calendar}
							onChange={(value) => setCalendar(value)}
						/>
						<p className="text-sm text-muted">{t.books.calendarHint}</p>
					</div>
					<p className="text-xs text-muted">{t.books.suggestedNote}</p>
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
