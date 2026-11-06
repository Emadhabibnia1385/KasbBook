import { useState } from "react";
import { tv } from "tailwind-variants";
import { BottomSheet, Button, Modal, useIsNarrow } from "@nyxon/nasim";
import { ArrowLeftIcon, ArrowRightIcon } from "@/shared/icons";
import { t } from "@/strings";
import {
	type CalendarKind,
	GREGORIAN_MONTHS,
	GREGORIAN_WEEK,
	gridFor,
	JALALI_MONTHS,
	JALALI_WEEK,
	monthOf,
	stepMonth,
} from "./calendar";
import { toPersianDigits } from "./jalaliDay";

const cell = tv({
	base: "grid size-10 place-items-center rounded-full text-sm tabular-nums transition-colors",
	variants: {
		state: {
			plain: "hover:bg-surface-secondary",
			today: "ring-1 ring-accent hover:bg-surface-secondary",
			picked: "bg-accent font-semibold text-accent-foreground",
		},
	},
});

/** The two calendars as a pair of buttons: one is always on. */
export function KindSwitch({
	kind,
	onChange,
}: {
	kind: CalendarKind;
	onChange: (kind: CalendarKind) => void;
}) {
	return (
		<fieldset className="m-0 inline-flex rounded-full border border-border p-0.5">
			<legend className="sr-only">{t.days.calendarKind}</legend>
			{(["jalali", "gregorian"] as const).map((option) => (
				<button
					key={option}
					type="button"
					aria-pressed={kind === option}
					className={`min-h-8 rounded-full px-3 text-sm ${kind === option ? "bg-accent text-accent-foreground" : "text-muted"}`}
					onClick={() => onChange(option)}
				>
					{option === "jalali" ? t.days.jalali : t.days.gregorian}
				</button>
			))}
		</fieldset>
	);
}

/**
 * A month to look at and pick a day from, in whichever calendar is chosen. It is a sheet on a phone and a
 * dialog on a desktop, like every other picker here, and choosing a day closes it.
 */
export function CalendarPopup({
	isOpen,
	onOpenChange,
	kind,
	onKindChange,
	selected,
	today,
	onPick,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	kind: CalendarKind;
	onKindChange: (kind: CalendarKind) => void;
	/** The ISO day now chosen, or "". */
	selected: string;
	today: string;
	onPick: (iso: string) => void;
}) {
	const narrow = useIsNarrow("md");
	// The month shown follows the chosen day (or today), and is the person's to move; changing the calendar
	// re-centres it on the same day.
	const anchor = selected || today;
	const [shown, setShown] = useState(() => monthOf(kind, anchor));
	const [lastKind, setLastKind] = useState(kind);
	if (lastKind !== kind) {
		setLastKind(kind);
		setShown(monthOf(kind, anchor));
	}
	const grid = gridFor(kind, shown.year, shown.month);
	const jalali = kind === "jalali";
	const title = jalali
		? `${JALALI_MONTHS[shown.month - 1]} ${toPersianDigits(String(shown.year))}`
		: `${GREGORIAN_MONTHS[shown.month - 1]} ${shown.year}`;
	const week = jalali ? JALALI_WEEK : GREGORIAN_WEEK;

	const body = (
		<div className="flex flex-col gap-3" dir={jalali ? "rtl" : "ltr"}>
			<div className="flex items-center justify-between">
				<Button
					isIconOnly
					variant="ghost"
					aria-label={t.days.nextMonth}
					onPress={() => setShown(stepMonth(shown.year, shown.month, 1))}
				>
					{jalali ? <ArrowLeftIcon aria-hidden /> : <ArrowRightIcon aria-hidden />}
				</Button>
				<span className="font-semibold" aria-live="polite">
					{title}
				</span>
				<Button
					isIconOnly
					variant="ghost"
					aria-label={t.days.previousMonth}
					onPress={() => setShown(stepMonth(shown.year, shown.month, -1))}
				>
					{jalali ? <ArrowRightIcon aria-hidden /> : <ArrowLeftIcon aria-hidden />}
				</Button>
			</div>
			<div className="grid grid-cols-7 justify-items-center gap-y-1 text-xs text-muted" aria-hidden>
				{week.map((letter, index) => (
					<span key={`${letter}${index}`}>{letter}</span>
				))}
			</div>
			<div className="grid grid-cols-7 justify-items-center gap-y-1">
				{Array.from({ length: grid.lead }, (_, i) => (
					<span key={`lead${i}`} />
				))}
				{grid.days.map((entry) => (
					<button
						key={entry.iso}
						type="button"
						aria-pressed={entry.iso === selected}
						aria-label={entry.iso}
						className={cell({
							state: entry.iso === selected ? "picked" : entry.iso === today ? "today" : "plain",
						})}
						onClick={() => {
							onPick(entry.iso);
							onOpenChange(false);
						}}
					>
						{jalali ? toPersianDigits(String(entry.day)) : entry.day}
					</button>
				))}
			</div>
			<div className="flex flex-wrap items-center justify-between gap-2" dir="rtl">
				<KindSwitch kind={kind} onChange={onKindChange} />
				<Button
					size="sm"
					variant="secondary"
					onPress={() => {
						onPick(today);
						onOpenChange(false);
					}}
				>
					{t.days.today}
				</Button>
			</div>
		</div>
	);

	return narrow ? (
		<BottomSheet isOpen={isOpen} onOpenChange={onOpenChange} title={t.days.pick}>
			{body}
		</BottomSheet>
	) : (
		<Modal isOpen={isOpen} onOpenChange={onOpenChange} title={t.days.pick} size="xs">
			{body}
		</Modal>
	);
}
