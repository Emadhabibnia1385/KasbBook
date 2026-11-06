import { useEffect, useRef } from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { SelectField, TextField } from "@nyxon/nasim";
import { useBooksListCurrencies } from "@/api/generated/books/books";
import type { BookRef } from "./Amount";
import { useQuotes } from "@/features/market/useQuotes";
import { multiply } from "@/features/payroll/decimal";
import { currencyName, formatMoney, toAscii } from "@/shared/format";
import { t } from "@/strings";

type MoneyValues = { amount: string; currency: string; rate: string };

/**
 * The currency, the amount and the rate of an entry, the same fields whether it is being recorded or
 * edited: the currency menu with what each is roughly worth, the amount with what it comes to in the
 * book's currency right under it, and the rate once the currency is another one.
 *
 * `initialCurrency` and `initialRate` are what the form opened with. Changing the currency clears the rate
 * and fills in the market's, and changing it back restores the rate the form opened with.
 */
export function MoneyFields({
	book,
	initialCurrency,
	initialRate,
}: {
	book: BookRef;
	initialCurrency: string;
	initialRate: string;
}) {
	const form = useFormContext<MoneyValues>();
	const currency = useWatch({ control: form.control, name: "currency" });
	const amountTyped = useWatch({ control: form.control, name: "amount" });
	const rateTyped = useWatch({ control: form.control, name: "rate" });
	const foreign = currency !== book.currency;

	const enabled = (useBooksListCurrencies(book.id).data ?? []).filter((option) => option.enabled);
	// What one unit of each other currency is worth in the book's own, written right after its name in
	// the menu, so the choice is made knowing roughly what it means. One request for all of them.
	const others = enabled
		.filter((option) => option.code !== book.currency)
		.map((option) => option.code);
	const worth = new Map(
		(useQuotes(others, book.currency, others.length > 0).data ?? []).map((q) => [q.code, q.value]),
	);
	const options = enabled.map((option) => {
		const value = worth.get(option.code);
		const approx = value ? `  ≈ ${formatMoney(value, book.currency)}` : "";
		return { value: option.code, label: `${option.name} (${option.code})${approx}` };
	});
	// An entry may be in a currency the book no longer ticks; it must still be shown and kept.
	if (!options.some((option) => option.value === currency)) {
		options.push({ value: currency, label: `${currencyName(currency)} (${currency})` });
	}

	const market = useQuotes([currency], book.currency, foreign);
	const quote = foreign ? market.data?.[0] : undefined;
	const previous = useRef(initialCurrency);
	useEffect(() => {
		if (currency === previous.current) return;
		previous.current = currency;
		// A rate belongs to its currency: the old one is not the new one's.
		form.setValue("rate", currency === initialCurrency ? initialRate : "", { shouldDirty: true });
	}, [currency, form, initialCurrency, initialRate]);
	useEffect(() => {
		if (foreign && quote && !form.getValues("rate")) {
			form.setValue("rate", quote.value, { shouldDirty: true });
		}
	}, [foreign, quote, form]);

	const rateOk = /^\d+(\.\d+)?$/.test(toAscii(rateTyped)) && Number(toAscii(rateTyped)) > 0;
	const amountOk = /^\d+(\.\d{1,4})?$/.test(toAscii(amountTyped));
	const equivalent =
		foreign && rateOk && amountOk ? multiply(toAscii(amountTyped), toAscii(rateTyped)) : null;

	return (
		<>
			{options.length > 1 ? (
				<SelectField name="currency" label={t.fx.currency} options={options} />
			) : null}
			<TextField
				name="amount"
				label={
					foreign ? `${t.transactions.amount} (${currencyName(currency)})` : t.transactions.amount
				}
				// Right under the amount, as it is typed: what this many of the chosen currency come to in the
				// book's own, at the rate below.
				description={equivalent ? `≈ ${formatMoney(equivalent, book.currency)}` : undefined}
				inputMode="decimal"
				dir="ltr"
				isRequired
			/>
			{foreign ? (
				<TextField
					name="rate"
					label={`${t.fx.rate} (${currencyName(currency)} → ${currencyName(book.currency)})`}
					// Said only when there is something to be careful about: a rate that is an estimate, or none.
					description={
						quote
							? quote.exact
								? undefined
								: t.fx.estimateWarning
							: market.isLoading
								? undefined
								: t.rateNote.missing
					}
					inputMode="decimal"
					dir="ltr"
					isRequired
				/>
			) : null}
		</>
	);
}
