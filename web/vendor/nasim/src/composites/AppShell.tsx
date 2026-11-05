'use client';

import { Drawer } from '@heroui/react';
import { type ReactNode, useState } from 'react';
import { Link } from 'react-aria-components';
import { tv } from 'tailwind-variants';
import { MenuIcon } from '../icons';
import { Button, Tooltip } from '../primitives';
import { useRegisterOverlay } from '../providers/overlays';
import { t } from '../strings';

const shell = tv({
  slots: {
    root: 'flex min-h-dvh bg-background text-foreground',
    aside:
      'sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-e border-border bg-surface lg:flex',
    brand: 'flex min-h-16 items-center px-4',
    nav: 'flex-1 overflow-y-auto px-3 py-2',
    footer: 'border-t border-border p-4',
    column: 'flex min-w-0 flex-1 flex-col',
    // Under Telegram's own bar or a notch the header grows by the inset instead of sliding under it.
    header:
      'sticky top-0 z-20 flex min-h-14 items-center gap-2 border-b border-border bg-surface px-3 pt-(--nasim-safe-top) sm:min-h-16 sm:gap-3 sm:px-4',
    topbar:
      'ms-auto flex min-w-0 flex-wrap items-center justify-end gap-2 py-1.5',
    main: 'mx-auto w-full max-w-7xl flex-1 px-page pt-6 pb-[calc(1.5rem+var(--nasim-safe-bottom))] focus:outline-none sm:pl-[max(1.5rem,var(--nasim-safe-left))] sm:pr-[max(1.5rem,var(--nasim-safe-right))]',
    list: 'flex flex-col gap-1',
    link: 'flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium no-underline outline-none transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
    mark: 'ms-auto h-5 w-1 rounded-full bg-accent',
  },
  variants: {
    current: {
      true: { link: 'bg-surface-tertiary text-foreground' },
      false: {
        link: 'text-muted hover:bg-surface-secondary hover:text-foreground',
      },
    },
  },
});

type NavItem = {
  href: string;
  label: string;
  /** Decorative; the label is the name. */
  icon?: ReactNode;
  /** The app knows the route: the item of the page on screen. */
  isCurrent?: boolean;
};

type AppShellProps = {
  /** The mark or wordmark: at the top of the sidebar and in the phone's bar. */
  brand: ReactNode;
  /** Names the navigation landmark. */
  navLabel: string;
  nav: NavItem[];
  /** The bar's end: a merchant switcher, an environment badge, the person's menu. */
  topbar?: ReactNode;
  /** Under the navigation: the attribution, a logout. */
  sidebarFooter?: ReactNode;
  /** Above the page: an offline notice, a sandbox warning. */
  banner?: ReactNode;
  children: ReactNode;
};

function NavList({
  nav,
  onNavigate,
}: {
  nav: NavItem[];
  onNavigate?: () => void;
}) {
  return (
    <ul className={shell().list()}>
      {nav.map((item) => {
        const slots = shell({ current: Boolean(item.isCurrent) });
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onPress={onNavigate}
              aria-current={item.isCurrent ? 'page' : undefined}
              className={slots.link()}
            >
              {item.icon ? (
                <span aria-hidden className="shrink-0">
                  {item.icon}
                </span>
              ) : null}
              <span className="truncate">{item.label}</span>
              {item.isCurrent ? (
                <span aria-hidden className={slots.mark()} />
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

// The frame of a dashboard: the sidebar from `lg` up, a bar with a menu button that opens the same
// navigation in a drawer below it, and the page in the <main id="main"> landmark.
export function AppShell({
  brand,
  navLabel,
  nav,
  topbar,
  sidebarFooter,
  banner,
  children,
}: AppShellProps) {
  const [open, setOpen] = useState(false);
  useRegisterOverlay(open, () => setOpen(false));
  const slots = shell();
  return (
    <div className={slots.root()}>
      <aside className={slots.aside()}>
        <div className={slots.brand()}>{brand}</div>
        <nav aria-label={navLabel} className={slots.nav()}>
          <NavList nav={nav} />
        </nav>
        {sidebarFooter ? (
          <div className={slots.footer()}>{sidebarFooter}</div>
        ) : null}
      </aside>

      <div className={slots.column()}>
        <header className={slots.header()}>
          <Tooltip>
            <Button
              isIconOnly
              variant="ghost"
              className="size-11 min-h-11 min-w-11 lg:hidden"
              aria-label={t.shell.openMenu}
              aria-expanded={open}
              onPress={() => setOpen(true)}
            >
              <MenuIcon />
            </Button>
            <Tooltip.Content placement="bottom">
              {t.shell.openMenu}
            </Tooltip.Content>
          </Tooltip>
          <div className="lg:hidden">{brand}</div>
          <div className={slots.topbar()}>{topbar}</div>
        </header>
        {banner}
        <main id="main" tabIndex={-1} className={slots.main()}>
          {children}
        </main>
      </div>

      <Drawer.Backdrop isOpen={open} onOpenChange={setOpen}>
        <Drawer.Content placement="right">
          <Drawer.Dialog aria-label={navLabel}>
            <Tooltip>
              <Drawer.CloseTrigger aria-label={t.shell.closeMenu} />
              <Tooltip.Content placement="bottom">
                {t.shell.closeMenu}
              </Tooltip.Content>
            </Tooltip>
            <Drawer.Header>
              <Drawer.Heading>{brand}</Drawer.Heading>
            </Drawer.Header>
            <Drawer.Body>
              <nav aria-label={navLabel}>
                <NavList nav={nav} onNavigate={() => setOpen(false)} />
              </nav>
              {sidebarFooter ? (
                <div className="mt-6 border-t border-border pt-4">
                  {sidebarFooter}
                </div>
              ) : null}
            </Drawer.Body>
          </Drawer.Dialog>
        </Drawer.Content>
      </Drawer.Backdrop>
    </div>
  );
}
