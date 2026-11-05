import { DateTimeField } from "@nyxon/nasim";
import { t } from "@/strings";

type DayFieldProps = { label: string; isRequired?: boolean } & (
	| { name: string }
	| { value: string; onChange: (value: string) => void; errorMessage?: string }
);

// Nasim's Jalali picker, named in Persian, for a field that means a day. Its value is a picker value:
// read it with `pickedDay`, set it with `toPicker`.
export function DayField(props: DayFieldProps) {
	return <DateTimeField {...props} calendarLabel={t.days.calendar} timeLabel={t.days.time} clearLabel={t.days.clear} />;
}
