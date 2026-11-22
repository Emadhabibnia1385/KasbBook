import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { FormRoot, Modal, SubmitButton, SwitchField, TextField, toast } from "@nyxon/nasim";
import {
	getBanksListMineQueryKey,
	useBanksCreate,
	useBanksUpdate,
} from "@/api/generated/banks/banks";
import type { BankAccountResponse, BookResponse } from "@/api/generated/model";
import { addMoney, subtractMoney } from "@/shared/decimal";
import { formatMoney, toAscii } from "@/shared/format";
import { refreshMoney, reportFailure } from "@/shared/mutations";
import { t } from "@/strings";
import { amountRule } from "@/features/transactions/rules";

// Only the bank and the holder are required. Every number is checked by the server (Luhn for a card,
// the check digits for a Sheba), so a typo is refused with a sentence rather than saved.
const schema = z.object({
	bank_name: z.string().trim().min(1, { error: t.banks.needBank }).max(80),
	holder_name: z.string().trim().min(1, { error: t.banks.needHolder }).max(120),
	display_name: z.string().trim().max(80),
	card_number: z.string().transform(toAscii),
	account_number: z.string().transform(toAscii),
	sheba: z.string().transform(toAscii),
	opening_balance: z.union([z.literal(""), amountRule]),
	// What the bank says the account holds now; when given, the opening balance is worked out from it.
	current_balance: z.union([z.literal(""), amountRule]),
	links: z.record(z.string(), z.boolean()),
});
type Values = z.input<typeof schema>;

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
	const sameUnit = books.filter((book) => book.currency === current.currency);
	const form = useForm<Values>({
		resolver: zodResolver(schema),
		defaultValues: {
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
			links: Object.fromEntries(sameUnit.map((book) => [book.id, book.id === current.id])),
		},
	});
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
								bank_name: values.bank_name,
								holder_name: values.holder_name,
								display_name: orNull(values.display_name),
								card_number: orNull(values.card_number),
								account_number: orNull(values.account_number),
								sheba: orNull(values.sheba),
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
								bank_name: values.bank_name,
								holder_name: values.holder_name,
								display_name: orNull(values.display_name),
								card_number: orNull(values.card_number),
								account_number: orNull(values.account_number),
								sheba: orNull(values.sheba),
								opening_balance: values.opening_balance || "0",
								currency: current.currency,
								book_ids: Object.entries(values.links)
									.filter(([, on]) => on)
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
			<TextField name="bank_name" label={t.banks.fieldBank} isRequired />
			<TextField name="holder_name" label={t.banks.fieldHolder} isRequired />
			<TextField
				name="display_name"
				label={t.banks.fieldDisplay}
				description={t.banks.fieldDisplayHint}
			/>
			<TextField name="card_number" label={t.banks.fieldCard} dir="ltr" inputMode="numeric" />
			<TextField name="account_number" label={t.banks.fieldAccount} dir="ltr" />
			<TextField name="sheba" label={t.banks.fieldSheba} dir="ltr" />
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
							<b className="text-foreground tabular-nums">{formatMoney(preview, bank.currency)}</b>
						</p>
					) : null}
				</>
			) : null}
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
