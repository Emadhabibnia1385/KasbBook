'use client';

import { useEffect, useRef } from 'react';
import { Link } from 'react-aria-components';
import { tv } from 'tailwind-variants';

const navTabs = tv({
  slots: {
    root: 'inline-flex max-w-full flex-wrap rounded-lg border border-field-border p-0.5',
    link: 'flex min-h-9 items-center rounded-md px-3 text-sm no-underline outline-none transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus',
  },
  variants: {
    current: {
      true: {},
      false: {},
    },
    // One row that scrolls sideways instead of wrapping into a second one on a narrow screen.
    scrollable: {
      true: {
        root: 'flex w-full min-w-0 max-w-full flex-nowrap overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden',
        link: 'shrink-0 whitespace-nowrap',
      },
      false: {},
    },
    // A lighter bar for tabs inside a page that already has a boxed one above: a line, not a second box.
    quiet: {
      true: {
        root: 'rounded-none border-0 border-b border-separator p-0',
        link: 'rounded-none border-b-2 px-4',
      },
      false: {},
    },
  },
  compoundVariants: [
    {
      current: true,
      quiet: false,
      class: { link: 'bg-accent font-semibold text-accent-foreground' },
    },
    {
      current: false,
      quiet: false,
      class: {
        link: 'text-muted hover:bg-surface-secondary hover:text-foreground',
      },
    },
    {
      current: true,
      quiet: true,
      class: { link: 'border-accent font-semibold text-foreground' },
    },
    {
      current: false,
      quiet: true,
      class: {
        link: 'border-transparent text-muted hover:text-foreground',
      },
    },
  ],
  defaultVariants: { scrollable: false, quiet: false },
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
  /** One row that scrolls sideways, with the current tab brought into view. */
  scrollable?: boolean;
  /** A line under the tabs instead of a box, for a second bar under a boxed one. */
  quiet?: boolean;
  className?: string;
};

// Sibling pages that share one menu entry, switched with a tab-looking bar. Each tab is a link to a page of
// its own (`aria-current`), not an in-page panel: `Tabs` is for panels.
export function NavTabs({
  label,
  items,
  scrollable,
  quiet,
  className,
}: NavTabsProps) {
  const ref = useRef<HTMLElement>(null);
  const current = items.find((item) => item.isCurrent)?.href;
  useEffect(() => {
    if (!scrollable) return;
    ref.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [scrollable, current]);
  const slots = navTabs({ scrollable, quiet });
  return (
    <nav ref={ref} aria-label={label} className={slots.root({ className })}>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={item.isCurrent ? 'page' : undefined}
          className={navTabs({
            current: Boolean(item.isCurrent),
            scrollable,
            quiet,
          }).link()}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
