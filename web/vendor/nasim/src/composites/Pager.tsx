'use client';

import { useEffect, useState } from 'react';
import { formatNumber, t } from '../strings';
import { Button } from '../primitives';

type PagerProps = {
  /** The page shown, counting from 1. */
  page: number;
  /** How many pages there are, when the list knows (a cursor-paged list does not). */
  pageCount?: number;
  /** Without `pageCount`: whether another page follows. */
  hasNext?: boolean;
  /** The next page is being fetched: «در حال به‌روزرسانی» joins the page number. */
  isFetching?: boolean;
  onPrevious: () => void;
  onNext: () => void;
  /** With `pageCount`: a number typed into the page box jumps straight to that page. */
  onPage?: (page: number) => void;
  className?: string;
};

// Persian and Arabic-Indic digits typed on a phone, as the ASCII digits Number() reads.
const asciiDigits = (text: string) =>
  text
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));

function PageBox({
  page,
  pageCount,
  onPage,
}: {
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
}) {
  const [text, setText] = useState(formatNumber(page));
  useEffect(() => setText(formatNumber(page)), [page]);
  const go = () => {
    const wanted = Number(asciiDigits(text).replace(/\D/g, ''));
    if (!Number.isFinite(wanted) || wanted < 1) return setText(formatNumber(page));
    const next = Math.min(pageCount, Math.max(1, Math.trunc(wanted)));
    setText(formatNumber(next));
    if (next !== page) onPage(next);
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      {t.pager.pageWord}
      <input
        type="text"
        inputMode="numeric"
        dir="ltr"
        aria-label={t.pager.goTo}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onFocus={(event) => event.target.select()}
        onBlur={go}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            go();
          }
        }}
        className="h-8 w-14 rounded-lg border border-separator bg-surface px-1 text-center text-sm text-foreground outline-none focus:border-accent"
      />
      {t.pager.ofWord} {formatNumber(pageCount)}
    </span>
  );
}

// Previous and next with the page said in words (Persian digits); the words are the live region.
export function Pager({
  page,
  pageCount,
  hasNext,
  isFetching,
  onPrevious,
  onNext,
  onPage,
  className,
}: PagerProps) {
  const last = pageCount !== undefined ? page >= pageCount : !hasNext;
  const where =
    pageCount !== undefined
      ? t.pager.pageOf(formatNumber(page), formatNumber(pageCount))
      : t.pager.page(formatNumber(page));
  return (
    <nav
      aria-label={t.pager.label}
      className={[
        'flex flex-wrap items-center justify-between gap-2',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="text-sm text-muted" aria-live="polite">
        {pageCount !== undefined && onPage ? (
          <PageBox page={page} pageCount={pageCount} onPage={onPage} />
        ) : (
          where
        )}
        {isFetching ? ` · ${t.pager.refreshing}` : ''}
      </span>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          size="sm"
          isDisabled={page <= 1}
          onPress={onPrevious}
        >
          {t.pager.previous}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          isDisabled={last}
          onPress={onNext}
        >
          {t.pager.next}
        </Button>
      </div>
    </nav>
  );
}
