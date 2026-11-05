import { useState } from "react";
import { useController } from "react-hook-form";
import { Button, TextField } from "@nyxon/nasim";
import { monthWindow } from "@/features/payroll/calendar";
import { t } from "@/strings";
import { pickedDay, toPicker } from "./dates";
import { formatJalaliDay, jalaliOfIso, parseJalaliDay, shiftIso, type DayParse } from "./jalaliDay";

type DayFieldProps = { label: string; isRequired?: boolean } & (
	| { name: string }
	| { value: string; onChange: (value: string) => void; errorMessage?: string }
);

function todayIso(now = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function problem(parse: Exclude<DayParse, { ok: true }>): string | undefined {
	const d = t.days;
	switch (parse.reason) {
		case "empty":
		case "partial":
			return undefined;
		case "year":
			return d.badYear;
		case "month":
			return d.badMonth;
		case "day":
			return `${d.badDay} ${parse.daysInMonth ?? ""}`.trim();
		default:
			return d.badFormat;
	}
}

// A day, typed in the Jalali calendar: «۱۴۰۵/۰۸/۱۵». The panel's value stays the picker's
// `YYYY-MM-DDTHH:mm` so every form that read it keeps reading it; only the box is day-only, because
// the time segment of the picker meant nothing for a day and confused everyone who met it.
function DayInput({
	label,
	isRequired,
	value,
	onChange,
	errorMessage,
}: {
	label: string;
	isRequired?: boolean | undefined;
	value: string;
	onChange: (value: string) => void;
	errorMessage?: string | undefined;
}) {
	const [text, setText] = useState(() => formatJalaliDay(pickedDay(value)));
	// A value that arrives from outside (a form reset, a chip) replaces what is typed, unless the
	// typed text already means that very day.
	const typed = parseJalaliDay(text);
	const typedIso = typed.ok ? typed.iso : "";
	const outside = pickedDay(value);
	if (outside !== typedIso && !(outside === "" && !typed.ok)) {
		const next = formatJalaliDay(outside);
		if (next !== text) setText(next);
	}

	const set = (iso: string) => {
		setText(formatJalaliDay(iso));
		onChange(toPicker(iso));
	};
	const today = todayIso();
	const mine = jalaliOfIso(today);
	const monthStart = mine
		? monthWindow(`${mine.year}-${String(mine.month).padStart(2, "0")}`).starts_on
		: today;
	const own = !typed.ok ? problem(typed) : undefined;

	return (
		<div className="flex flex-col gap-2">
			<TextField
				label={label}
				isRequired={isRequired}
				value={text}
				inputMode="numeric"
				dir="ltr"
				placeholder={t.days.placeholder}
				errorMessage={errorMessage ?? own}
				onChange={(next: string) => {
					setText(next);
					const parsed = parseJalaliDay(next);
					onChange(parsed.ok ? toPicker(parsed.iso) : "");
				}}
			/>
			<div className="flex flex-wrap gap-2">
				<Button size="sm" variant="secondary" onPress={() => set(today)}>
					{t.days.today}
				</Button>
				<Button size="sm" variant="secondary" onPress={() => set(shiftIso(today, -1))}>
					{t.days.yesterday}
				</Button>
				<Button size="sm" variant="secondary" onPress={() => set(monthStart)}>
					{t.days.monthStart}
				</Button>
			</div>
		</div>
	);
}

function BoundDayInput({
	name,
	label,
	isRequired,
}: {
	name: string;
	label: string;
	isRequired?: boolean | undefined;
}) {
	const { field, fieldState } = useController({ name });
	return (
		<DayInput
			label={label}
			isRequired={isRequired}
			value={typeof field.value === "string" ? field.value : ""}
			onChange={field.onChange}
			errorMessage={fieldState.error?.message}
		/>
	);
}

export function DayField(props: DayFieldProps) {
	if ("name" in props)
		return <BoundDayInput name={props.name} label={props.label} isRequired={props.isRequired} />;
	return (
		<DayInput
			label={props.label}
			isRequired={props.isRequired}
			value={props.value}
			onChange={props.onChange}
			errorMessage={props.errorMessage}
		/>
	);
}
