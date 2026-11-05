import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';
import { ChevronDownIcon } from '../icons';

const collapsible = tv({
  slots: {
    root: 'group rounded-xl border border-border bg-surface',
    summary:
      'flex min-h-12 cursor-pointer list-none items-center gap-3 rounded-xl px-4 py-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden',
    chevron:
      'shrink-0 text-muted transition-transform group-open:rotate-180 motion-reduce:transition-none',
    title: 'font-semibold text-foreground',
    description: 'text-sm text-muted',
    body: 'flex flex-col gap-4 border-t border-border p-4',
  },
});

type CollapsibleProps = {
  /** What is inside: the summary says it before the section opens. */
  title: ReactNode;
  /** One short line under the title, visible while collapsed. */
  description?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
  'data-testid'?: string;
};

// Advanced or rarely used options in a native <details>: keyboard and screen readers for free, no client JS.
export function Collapsible({
  title,
  description,
  defaultOpen,
  className,
  children,
  'data-testid': testId,
}: CollapsibleProps) {
  const slots = collapsible();
  return (
    <details
      className={slots.root({ className })}
      open={defaultOpen}
      data-testid={testId}
    >
      <summary className={slots.summary()}>
        <span aria-hidden className={slots.chevron()}>
          <ChevronDownIcon />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className={slots.title()}>{title}</span>
          {description ? (
            <span className={slots.description()}>{description}</span>
          ) : null}
        </span>
      </summary>
      <div className={slots.body()}>{children}</div>
    </details>
  );
}
