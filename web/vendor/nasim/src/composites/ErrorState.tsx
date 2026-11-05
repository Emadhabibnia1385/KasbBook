'use client';

import { type ReactNode, type Ref, useEffect, useState } from 'react';
import { tv } from 'tailwind-variants';
import { formatNumber, t } from '../strings';
import { ErrorIcon } from '../icons';
import { Button, LinkButton } from '../primitives';

const errorState = tv({
  slots: {
    root: 'mx-auto flex max-w-sm flex-col items-center gap-3 px-4 py-10 text-center',
    // Only what happened is announced; the buttons below are not part of the alert.
    alert: 'flex flex-col items-center gap-3',
    icon: 'grid size-14 place-items-center rounded-full bg-danger-soft text-danger-soft-foreground [&>svg]:size-7',
    title: 'text-lg font-semibold text-foreground',
    message: 'text-sm text-muted text-pretty',
    actions: 'mt-2 flex w-full flex-col gap-2',
    code: 'text-xs text-muted',
  },
});

type ErrorStateProps = {
  /** Defaults to «بارگذاری انجام نشد». */
  title?: string;
  /** What went wrong and what to do; defaults to a connection hint. */
  message?: string;
  onRetry?: () => void;
  /** Seconds before the retry works, e.g. a 429's Retry-After: the button counts them down. */
  retryIn?: number;
  /** A support link (Telegram or in-app); shown next to the retry button. */
  supportHref?: string;
  /** The request id from the API error, so support can find the failure. */
  requestId?: string;
  /** Detail under the message (the fields the server refused), announced with it. */
  children?: ReactNode;
  /** Heading level: "h1" when the state is the whole page, "h2" (default) inside one. */
  as?: 'h1' | 'h2';
  /** A ref to the title, which takes focus when a screen swaps this state in. */
  titleRef?: Ref<HTMLHeadingElement>;
};

export function ErrorState({
  title = t.state.errorTitle,
  message = t.state.errorMessage,
  onRetry,
  retryIn,
  supportHref,
  requestId,
  children,
  as: Heading = 'h2',
  titleRef,
}: ErrorStateProps) {
  const slots = errorState();
  return (
    <div className={slots.root()}>
      <span aria-hidden className={slots.icon()}>
        <ErrorIcon />
      </span>
      <div role="alert" className={slots.alert()}>
        <Heading
          ref={titleRef}
          tabIndex={titleRef ? -1 : undefined}
          className={slots.title()}
        >
          {title}
        </Heading>
        <p className={slots.message()}>{message}</p>
        {children}
      </div>
      {onRetry || supportHref ? (
        <div className={slots.actions()}>
          {onRetry ? <RetryButton onRetry={onRetry} wait={retryIn} /> : null}
          {supportHref ? (
            <LinkButton
              href={supportHref}
              variant="outline"
              size="lg"
              fullWidth
            >
              {t.state.contactSupport}
            </LinkButton>
          ) : null}
        </div>
      ) : null}
      {requestId ? (
        <p className={slots.code()}>
          {t.state.trackingCode}: <bdi className="font-mono">{requestId}</bdi>
        </p>
      ) : null}
    </div>
  );
}

function RetryButton({
  onRetry,
  wait = 0,
}: {
  onRetry: () => void;
  wait?: number;
}) {
  const [left, setLeft] = useState(Math.ceil(wait));
  const counting = left > 0;
  useEffect(() => {
    if (!counting) return;
    const timer = setInterval(
      () => setLeft((seconds) => Math.max(0, seconds - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, [counting]);
  return (
    <Button size="lg" fullWidth isDisabled={counting} onPress={onRetry}>
      {counting ? t.state.retryIn(formatNumber(left)) : t.common.retry}
    </Button>
  );
}
