import { useState } from "react";
import { useController } from "react-hook-form";
import { Button, TextField } from "@nyxon/nasim";
import { monthWindow } from "@/features/payroll/calendar";
import { CalendarIcon } from "@/shared/icons";
import { t } from "@/strings";
import { CalendarPopup, KindSwitch } from "./CalendarPopup";
import { type CalendarKind, parseGregorianDay, writeDay } from "./calendar";
import { pickedDay, toPicker } from "./dates";
import { type DayParse, jalaliOfIso, parseJalaliDay, shiftIso } from "./jalaliDay";

type DayFieldProps = { label: string; isRequired?: boolean } & (
	| { name: string }
	| { value: string; onChange: (value: string) => void; errorMessage?: string }
);

function todayIso(now = new Date()): string {
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const KIND_KEY = "kasbbook.calendar";

/** Which calendar the person types and picks in; remembered, because it is a habit, not a choice per field. */
function useCalendarKind(): [CalendarKind, (kind: CalendarKind) => void] {
	const [kind, setKind] = useState<CalendarKind>(() => {
		try {
			return localStorage.getItem(KIND_KEY) === "gregorian" ? "gregorian" : "jalali";
		} catch {
			return "jalali";
		}
	});
	return [
		kind,
		(next) => {
			setKind(next);
			try {
				localStorage.setItem(KIND_KEY, next);
			} catch {
				// the choice lasts until the page is closed
			}
		},
	];
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

/** A typed day in one calendar: its ISO day, or nothing and the reason it is not one yet. */
function read(kind: CalendarKind, text: string): { iso: string; message?: string | undefined } {
	if (kind === "jalali") {
		const parsed = parseJalaliDay(text);
		return parsed.ok ? { iso: parsed.iso } : { iso: "", message: problem(parsed) };
	}
	const parsed = parseGregorianDay(text);
	if (parsed.ok) return { iso: parsed.iso };
	return {
		iso: "",
		message: parsed.empty || parsed.partial ? undefined : t.days.badFormatGregorian,
	};
}

// A day, typed or picked, in the Jalali or the Gregorian calendar. The panel's value stays the picker's
// `YYYY-MM-DDTHH:mm` so every form that read it keeps reading it; the calendar only changes how it is
// written and chosen, never what it is.
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
	const [kind, setKind] = useCalendarKind();
	const [open, setOpen] = useState(false);
	const [text, setText] = useState(() => writeDay(kind, pickedDay(value)));
	const [lastKind, setLastKind] = useState(kind);
	// A value that arrives from outside (a form reset, a chip, the popup) replaces what is typed, unless the
	// typed text already means that very day. Switching calendar rewrites the same day in the other one.
	const typed = read(kind, text);
	const outside = pickedDay(value);
	if (lastKind !== kind) {
		setLastKind(kind);
		setText(writeDay(kind, outside));
	} else if (outside !== typed.iso && !(outside === "" && !typed.iso)) {
		const next = writeDay(kind, outside);
		if (next !== text) setText(next);
	}

	const set = (iso: string) => {
		setText(writeDay(kind, iso));
		onChange(toPicker(iso));
	};
	const today = todayIso();
	const mine = jalaliOfIso(today);
	const monthStart = mine
		? monthWindow(`${mine.year}-${String(mine.month).padStart(2, "0")}`).starts_on
		: today;

	return (
		<div className="flex flex-col gap-2">
			<div className="flex items-end gap-2">
				<div className="min-w-0 flex-1">
					<TextField
						label={label}
						isRequired={isRequired}
						value={text}
						inputMode="numeric"
						dir="ltr"
						placeholder={kind === "jalali" ? t.days.placeholder : t.days.placeholderGregorian}
						errorMessage={errorMessage ?? typed.message}
						onChange={(next: string) => {
							setText(next);
							const parsed = read(kind, next);
							onChange(parsed.iso ? toPicker(parsed.iso) : "");
						}}
					/>
				</div>
				<Button
					isIconOnly
					variant="secondary"
					aria-label={t.days.pick}
					className="size-11 shrink-0"
					onPress={() => setOpen(true)}
				>
					<CalendarIcon aria-hidden />
				</Button>
			</div>
			<div className="flex flex-wrap items-center gap-2">
				<KindSwitch kind={kind} onChange={setKind} />
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
			<CalendarPopup
				isOpen={open}
				onOpenChange={setOpen}
				kind={kind}
				onKindChange={setKind}
				selected={outside}
				today={today}
				onPick={set}
			/>
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
