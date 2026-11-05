'use client';

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
  className?: string;
};

// Previous and next with the page said in words (Persian digits); the words are the live region.
export function Pager({
  page,
  pageCount,
  hasNext,
  isFetching,
  onPrevious,
  onNext,
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
        {where}
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
