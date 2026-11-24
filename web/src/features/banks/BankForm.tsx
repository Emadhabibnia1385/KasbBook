import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
	FormRoot,
	Modal,
	SelectField,
	SubmitButton,
	SwitchField,
	TextField,
	toast,
} from "@nyxon/nasim";
import {
	getBanksListMineQueryKey,
	useBanksCreate,
	useBanksListMine,
	useBanksUpdate,
} from "@/api/generated/banks/banks";
import type { BankAccountResponse, BookResponse } from "@/api/generated/model";
import { addMoney, subtractMoney } from "@/shared/decimal";
import { currencyName, formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { amountRule } from "@/features/transactions/rules";
import { isSharedBook } from "./privacy";

// Only the bank and the holder are required, and not even those for a cash wallet. Every number is checked
// by the server (Luhn for a card, the check digits for a Sheba), so a typo is refused with a sentence.
const schema = z
	.object({
		is_cash: z.boolean(),
		currency: z.string().min(1),
		bank_name: z.string().trim().max(80),
		holder_name: z.string().trim().max(120),
		display_name: z.string().trim().max(80),
		card_number: z.string().transform(toAscii),
		account_number: z.string().transform(toAscii),
		sheba: z.string().transform(toAscii),
		opening_balance: z.union([z.literal(""), amountRule]),
		// What the bank says the account holds now; when given, the opening balance is worked out from it.
		current_balance: z.union([z.literal(""), amountRule]),
		links: z.record(z.string(), z.boolean()),
	})
	.superRefine((value, ctx) => {
		if (value.is_cash) return;
		if (!value.bank_name)
			ctx.addIssue({ code: "custom", path: ["bank_name"], message: t.banks.needBank });
		if (!value.holder_name)
			ctx.addIssue({ code: "custom", path: ["holder_name"], message: t.banks.needHolder });
	});
type Values = z.input<typeof schema>;

// The units an account can be kept in: toman and rial, the book's own too if it is neither.
const UNITS = [
	{ value: "IRT", label: currencyName("IRT") },
	{ value: "IRR", label: currencyName("IRR") },
];

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

function Fields({
	bank,
	books,
	current,
	onDone,
}: {
	bank: BankAccountResponse | null;
	/** The books an account may be added to: the ones counting in the same unit as this one. */
	books: BookResponse[];
	current: BookResponse;
	onDone: () => void;
}) {
	const queryClient = useQueryClient();
	const create = useBanksCreate();
	const update = useBanksUpdate();
	const mine = useBanksListMine().data ?? [];
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
			is_cash: bank?.kind === "cash",
			currency: bank?.currency ?? current.currency,
			bank_name: bank?.bank_name ?? "",
			holder_name: bank?.holder_name ?? "",
			display_name: bank?.display_name ?? "",
			card_number: bank?.card_number ?? "",
			account_number: bank?.account_number ?? "",
			sheba: bank?.sheba ?? "",
			opening_balance:
				bank && Number(bank.opening_balance) !== 0
					? bank.opening_balance.replace(/\.?0+$/, "")
					: "",
			current_balance: "",
			links: Object.fromEntries(books.map((book) => [book.id, book.id === current.id])),
		},
	});
	// A cash wallet has no bank, holder or numbers; an account is kept in one unit, and only books in that unit take it.
	const isCash = Boolean(useWatch({ control: form.control, name: "is_cash" }));
	const unit = useWatch({ control: form.control, name: "currency" }) ?? current.currency;
	const sameUnit = books.filter((book) => book.currency === unit);
	const units = UNITS.some((option) => option.value === current.currency)
		? UNITS
		: [{ value: current.currency, label: currencyName(current.currency) }, ...UNITS];
	const wallet = mine.find((row) => row.kind === "cash" && row.currency === unit);
	// What the opening balance becomes if the bank's figure is saved: that figure minus everything the books
	// put in or took out, across every book that uses the account.
	const typed = toAscii(useWatch({ control: form.control, name: "current_balance" }) ?? "");
	const preview =
		bank && /^\d+(\.\d{1,4})?$/.test(typed)
			? subtractMoney(typed, addMoney("0", ...bank.shares.map((share) => share.balance)))
			: null;
	return (
		<FormRoot
			form={form}
			className="flex flex-col gap-4"
			onSubmit={async (raw) => {
				const values = schema.parse(raw);
				try {
					if (bank) {
						await update.mutateAsync({
							bankId: bank.id,
							data: {
								...(bank.kind === "cash"
									? {}
									: {
											bank_name: values.bank_name,
											holder_name: values.holder_name,
											card_number: orNull(values.card_number),
											account_number: orNull(values.account_number),
											sheba: orNull(values.sheba),
										}),
								display_name: orNull(values.display_name),
								// Either the real balance (the opening one is worked out from it) or the opening one.
								...(values.current_balance
									? { current_balance: values.current_balance }
									: { opening_balance: values.opening_balance || "0" }),
							},
						});
						toast.success(t.banks.saved);
					} else {
						await create.mutateAsync({
							data: {
								kind: values.is_cash ? "cash" : "bank",
								...(values.is_cash
									? {}
									: {
											bank_name: values.bank_name,
											holder_name: values.holder_name,
											card_number: orNull(values.card_number),
											account_number: orNull(values.account_number),
											sheba: orNull(values.sheba),
										}),
								display_name: orNull(values.display_name),
								opening_balance: values.opening_balance || "0",
								currency: values.currency,
								book_ids: Object.entries(values.links)
									.filter(
										([id, on]) =>
											on && books.some((b) => b.id === id && b.currency === values.currency),
									)
									.map(([id]) => id),
							},
						});
						toast.success(t.banks.created);
					}
					await Promise.all([
						queryClient.invalidateQueries({ queryKey: getBanksListMineQueryKey() }),
						refreshMoney(queryClient, current.id),
					]);
					onDone();
				} catch (error) {
					reportFailure(error);
				}
			}}
		>
			{bank ? null : (
				<>
					<SwitchField
						name="is_cash"
						label={t.banks.cashSwitch}
						description={t.banks.cashSwitchHint}
					/>
					{isCash && wallet ? (
						<p className="text-sm text-warning">
							{wallet.is_active ? t.banks.cashExists : t.banks.cashReturns}
						</p>
					) : null}
					<SelectField name="currency" label={t.banks.fieldUnit} options={units} />
				</>
			)}
			{isCash || bank?.kind === "cash" ? null : (
				<>
					<TextField name="bank_name" label={t.banks.fieldBank} isRequired />
					<TextField name="holder_name" label={t.banks.fieldHolder} isRequired />
				</>
			)}
			<TextField
				name="display_name"
				label={t.banks.fieldDisplay}
				description={
					isCash || bank?.kind === "cash" ? t.banks.fieldDisplayCash : t.banks.fieldDisplayHint
				}
			/>
			{isCash || bank?.kind === "cash" ? null : (
				<>
					<TextField name="card_number" label={t.banks.fieldCard} dir="ltr" inputMode="numeric" />
					<TextField name="account_number" label={t.banks.fieldAccount} dir="ltr" />
					<TextField name="sheba" label={t.banks.fieldSheba} dir="ltr" />
				</>
			)}
			{/* The opening balance and the bank's real balance are the account's own, whole: not for a team book to see or set. */}
			{isSharedBook(current) ? null : (
				<>
					<TextField
						name="opening_balance"
						label={t.banks.fieldOpening}
						description={t.banks.fieldOpeningHint}
						inputMode="decimal"
					/>
					{bank ? (
						<>
							<TextField
								name="current_balance"
								label={t.banks.fieldCurrent}
								description={t.banks.fieldCurrentHint}
								inputMode="decimal"
							/>
							{preview !== null ? (
								<p className="text-sm text-muted">
									{t.banks.currentPreview}:{" "}
									<b className="text-foreground tabular-nums">
										{formatMoney(preview, bank.currency)}
									</b>
								</p>
							) : null}
						</>
					) : null}
				</>
			)}
			{bank ? null : (
				<fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
					<legend className="mb-1 text-sm font-medium">{t.banks.useIn}</legend>
					<p className="text-xs text-muted">{t.banks.useInHint}</p>
					{sameUnit.map((book) => (
						<SwitchField key={book.id} name={`links.${book.id}`} label={book.name} />
					))}
				</fieldset>
			)}
			<SubmitButton>{t.common.save}</SubmitButton>
		</FormRoot>
	);
}

/** Adding an account, or changing one you own. Opened fresh each time, so no old values linger. */
export function BankDialog({
	isOpen,
	onOpenChange,
	bank,
	books,
	current,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	bank: BankAccountResponse | null;
	books: BookResponse[];
	current: BookResponse;
}) {
	return (
		<Modal
			isOpen={isOpen}
			onOpenChange={onOpenChange}
			title={bank ? t.banks.edit : t.banks.add}
			size="lg"
		>
			{isOpen ? (
				<Fields
					key={bank?.id ?? "new"}
					bank={bank}
					books={books}
					current={current}
					onDone={() => onOpenChange(false)}
				/>
			) : null}
		</Modal>
	);
}
