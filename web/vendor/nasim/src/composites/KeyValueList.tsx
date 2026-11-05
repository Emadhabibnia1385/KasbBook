import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';

const keyValueList = tv({
  slots: {
    root: 'flex flex-col divide-y divide-separator',
    row: 'flex gap-x-4 gap-y-1 py-3 first:pt-0 last:pb-0',
    label: 'shrink-0 text-sm text-muted',
    value: 'min-w-0 break-words text-sm font-medium text-foreground',
  },
  variants: {
    layout: {
      // label at the start, value at the end: balances, dates, plan names. A long value wraps under its label.
      split: {
        row: 'flex-wrap items-baseline justify-between',
        value: 'text-end',
      },
      // label above value: long values such as links and addresses
      stacked: { row: 'flex-col' },
      // pairs in two columns from `sm` up, label above value: the details of one record
      grid: {
        root: 'grid gap-x-6 gap-y-3 divide-y-0 sm:grid-cols-2',
        row: 'min-w-0 flex-col gap-0.5 py-0',
        label: 'text-xs',
        value: 'font-normal',
      },
    },
    ltr: { true: { value: 'break-all font-mono' } },
    numeric: { true: { value: 'tabular-nums' } },
  },
  // LTR text: in two columns the value is at the row's end (left in RTL); stacked, at the start.
  compoundVariants: [
    { layout: 'split', ltr: true, class: { value: 'text-start' } },
    { layout: 'stacked', ltr: true, class: { value: 'text-end' } },
  ],
  defaultVariants: { layout: 'split' },
});

type KeyValueItem = {
  /** Only needed when labels repeat and rows can reorder; rows are keyed by position otherwise. */
  id?: string;
  label: ReactNode;
  value: ReactNode;
  /** Technical values (IDs, addresses, links): left to right, monospace, never wrapped mid-word. */
  ltr?: boolean;
  /** Numbers that line up with other rows: balances, prices, countdowns. */
  numeric?: boolean;
};

type KeyValueListProps = {
  /** `false`, `null` and `undefined` are skipped, so a row that exists only sometimes is `cond && { … }`. */
  items: readonly (KeyValueItem | false | null | undefined)[];
  layout?: 'split' | 'stacked' | 'grid';
  className?: string;
};

export function KeyValueList({ items, layout, className }: KeyValueListProps) {
  return (
    <dl className={keyValueList({ layout }).root({ className })}>
      {items.map((item, index) => {
        if (!item) return null;
        const { id, label, value, ltr, numeric } = item;
        const slots = keyValueList({ layout, ltr, numeric });
        return (
          <div key={id ?? index} className={slots.row()}>
            <dt className={slots.label()}>{label}</dt>
            <dd className={slots.value()} dir={ltr ? 'ltr' : undefined}>
              {value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
