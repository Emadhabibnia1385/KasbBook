import {
  CalendarDateTime,
  GregorianCalendar,
  PersianCalendar,
  toCalendar,
} from '@internationalized/date';

/**
 * Bridges a form value (`YYYY-MM-DDTHH:mm`, Gregorian, device local time) and the Persian-calendar
 * value shown by the date picker. Only the display calendar changes; the value a form stores does not.
 */
const LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2})?$/;

export function toJalaliValue(value: string): CalendarDateTime | null {
  const match = LOCAL.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute] = match.slice(1).map(Number) as [
    number,
    number,
    number,
    number,
    number,
  ];
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31 ||
    hour > 23 ||
    minute > 59
  )
    return null;
  const gregorian = new CalendarDateTime(year, month, day, hour, minute);
  // CalendarDateTime constrains out-of-range days; reject instead of silently moving the date.
  if (gregorian.day !== day || gregorian.month !== month) return null;
  return toCalendar(gregorian, new PersianCalendar());
}

export function fromJalaliValue(value: CalendarDateTime | null): string {
  if (!value) return '';
  const gregorian = toCalendar(value, new GregorianCalendar());
  const pad = (n: number, width = 2) => String(n).padStart(width, '0');
  return `${pad(gregorian.year, 4)}-${pad(gregorian.month)}-${pad(gregorian.day)}T${pad(gregorian.hour)}:${pad(gregorian.minute)}`;
}
