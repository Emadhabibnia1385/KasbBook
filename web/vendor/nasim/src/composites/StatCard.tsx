import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';

const statCard = tv({
  slots: {
    root: 'flex min-w-0 flex-col gap-2 rounded-2xl border border-border bg-surface p-4 shadow-surface sm:p-5',
    head: 'flex items-center justify-between gap-2',
    label: 'text-sm font-medium text-muted',
    icon: 'text-muted',
    value: 'text-2xl leading-tight font-bold text-foreground tabular-nums',
    hint: 'text-xs leading-6 text-muted',
  },
});

type StatCardProps = {
  /** What is counted. */
  label: ReactNode;
  /** The figure: a formatted number or an amount with its unit. */
  value: ReactNode;
  /** Its scope or unit, in words. */
  hint?: ReactNode;
  /** Under the hint (a comparison with the last period); may hold paragraphs of its own. */
  footer?: ReactNode;
  icon?: ReactNode;
  /** The label's element: a heading when the tile titles a section of the page. */
  as?: 'p' | 'h2' | 'h3';
  className?: string;
  'data-testid'?: string;
};

// A key figure: label, tabular value and a line of context. Server-renderable.
export function StatCard({
  label,
  value,
  hint,
  footer,
  icon,
  as: Label = 'p',
  className,
  'data-testid': testId,
}: StatCardProps) {
  const slots = statCard();
  return (
    <div className={slots.root({ className })} data-testid={testId}>
      <div className={slots.head()}>
        <Label className={slots.label()}>{label}</Label>
        {icon ? (
          <span aria-hidden className={slots.icon()}>
            {icon}
          </span>
        ) : null}
      </div>
      <div className={slots.value()}>{value}</div>
      {hint ? <p className={slots.hint()}>{hint}</p> : null}
      {footer}
    </div>
  );
}
