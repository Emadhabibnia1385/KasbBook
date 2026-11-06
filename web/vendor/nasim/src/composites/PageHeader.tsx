'use client';

import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';
import { t } from '../strings';
import { BackIcon } from '../icons';
import { LinkButton } from '../primitives';
import { useNativeBack } from '../providers/NasimContext';
import { useAnnouncePageHeading } from '../providers/pageHeading';

const pageHeader = tv({
  slots: {
    root: 'flex flex-wrap items-start gap-3',
    text: 'flex min-w-0 flex-[1_1_16rem] flex-col gap-1',
    title: 'font-bold text-foreground',
    description: 'text-sm text-muted text-pretty',
    meta: 'mt-1 flex flex-wrap items-center gap-2 text-xs text-muted',
    // max-w-full lets a long row of buttons wrap inside a phone's width instead of widening the page
    actions: 'flex max-w-full flex-wrap items-center gap-2',
  },
  variants: {
    size: {
      page: { title: 'text-2xl' },
      section: { title: 'text-lg font-semibold' },
    },
    // Under Telegram's own buttons (fullscreen Mini App) or a device notch.
    placement: {
      content: {},
      top: { root: 'px-safe pt-(--nasim-safe-top)' },
    },
    // The way back is 44px tall: the title takes the same height so its line is centred on it.
    back: {
      true: { title: 'flex min-h-11 items-center' },
      false: {},
    },
    // The actions stay on the title's row, at its far end, however narrow the page is.
    inline: {
      true: { root: 'flex-nowrap items-center', text: 'flex-[1_1_0%]', actions: 'shrink-0' },
      false: {},
    },
  },
  defaultVariants: { size: 'page', placement: 'content', back: false, inline: false },
});

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  /** A small line under the description: a status chip, the last update, the environment. */
  meta?: ReactNode;
  /** Where «بازگشت» leads; omit on top-level pages; not drawn when the host has its own back. */
  backHref?: string;
  /** Buttons at the far end, e.g. a primary action. */
  actions?: ReactNode;
  /** Keep the actions on the title's row instead of letting them wrap under it on a narrow page. */
  inlineActions?: boolean;
  /** Heading level: one h1 per page, h2 for a section header. */
  as?: 'h1' | 'h2' | 'h3';
  size?: 'page' | 'section';
  /** "top" when nothing is above it (clears the safe areas); inside the shell keep "content". */
  placement?: 'content' | 'top';
  className?: string;
};

export function PageHeader({
  title,
  description,
  meta,
  backHref,
  actions,
  inlineActions,
  as: Heading = 'h1',
  size,
  placement,
  className,
}: PageHeaderProps) {
  const nativeBack = useNativeBack();
  useAnnouncePageHeading(Heading === 'h1' ? title : undefined);
  const showBack = Boolean(backHref) && !nativeBack;
  const slots = pageHeader({ size, placement, back: showBack, inline: inlineActions });
  return (
    <header className={slots.root({ className })}>
      {showBack ? (
        <LinkButton
          isIconOnly
          href={backHref ?? '/'}
          variant="ghost"
          size="lg"
          className="size-11"
          aria-label={t.common.back}
        >
          <BackIcon className="rtl:rotate-180" />
        </LinkButton>
      ) : null}
      <div className={slots.text()}>
        <Heading className={slots.title()}>{title}</Heading>
        {description ? (
          <p className={slots.description()}>{description}</p>
        ) : null}
        {meta ? <div className={slots.meta()}>{meta}</div> : null}
      </div>
      {actions ? <div className={slots.actions()}>{actions}</div> : null}
    </header>
  );
}
