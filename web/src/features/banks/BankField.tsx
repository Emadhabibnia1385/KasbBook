import { useEffect } from "react";
import { useController } from "react-hook-form";
import { SelectField } from "@nyxon/nasim";
import { useBanksListForBook } from "@/api/generated/banks/banks";
import { t } from "@/strings";

/**
 * The account a transaction goes through, chosen from the book's own. It starts on the book's default
 * (or on «بدون حساب» when there is none) and can be changed for this one transaction. Nothing shows when
 * the book has no accounts, or when the money is in another currency, which no account holds.
 */
export function BankField({
	name,
	bookId,
	hidden,
	noneLabel,
	label,
}: {
	name: string;
	bookId: string;
	hidden?: boolean;
	/** What «no account» is called where it means something more specific than «بدون حساب». */
	noneLabel?: string;
	label?: string;
}) {
	const { field } = useController({ name });
	const query = useBanksListForBook(bookId);
	const rows = query.data;
	const value = typeof field.value === "string" ? field.value : "";
	const standing = rows?.find((row) => row.is_default && row.is_active);

	// Until the list is here the value stays empty (the server then picks the default itself); once it is, an
	// untouched field shows what that choice is.
	useEffect(() => {
		if (rows && value === "") field.onChange(standing ? standing.id : "none");
	}, [rows, value, standing, field]);

	if (hidden || !rows || rows.length === 0) return null;
	const options = [
		{ value: "none", label: noneLabel ?? t.banks.none },
		...rows
			.filter((row) => row.is_active || row.id === value)
			.map((row) => ({
				value: row.id,
				label: [
					row.title,
					row.card_last4,
					row.is_default ? `(${t.banks.defaultMark})` : null,
					row.is_active ? null : `(${t.banks.inactiveMark})`,
				]
					.filter(Boolean)
					.join(" "),
			})),
	];
	return <SelectField name={name} label={label ?? t.banks.account} options={options} />;
}
