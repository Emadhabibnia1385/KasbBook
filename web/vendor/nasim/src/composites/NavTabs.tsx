'use client';

import { Link } from 'react-aria-components';
import { tv } from 'tailwind-variants';

const navTabs = tv({
  slots: {
    root: 'inline-flex max-w-full flex-wrap rounded-lg border border-field-border p-0.5',
    link: 'flex min-h-9 items-center rounded-md px-3 text-sm no-underline outline-none transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus',
  },
  variants: {
    current: {
      true: { link: 'bg-accent font-semibold text-accent-foreground' },
      false: {
        link: 'text-muted hover:bg-surface-secondary hover:text-foreground',
      },
    },
  },
});

type NavTab = {
  href: string;
  label: string;
  /** The app knows the route: the tab of the page on screen. */
  isCurrent?: boolean;
};

type NavTabsProps = {
  /** Names the navigation landmark. */
  label: string;
  items: readonly NavTab[];
  className?: string;
};

// Sibling pages that share one menu entry, switched with a tab-looking bar. Each tab is a link to a page of
// its own (`aria-current`), not an in-page panel: `Tabs` is for panels.
export function NavTabs({ label, items, className }: NavTabsProps) {
  return (
    <nav aria-label={label} className={navTabs().root({ className })}>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={item.isCurrent ? 'page' : undefined}
          className={navTabs({ current: Boolean(item.isCurrent) }).link()}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
