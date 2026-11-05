'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckIcon, CopyIcon, DangerIcon } from '../icons';
import { Button, type ButtonProps } from '../primitives';
import { t } from '../strings';

// The clipboard API first; a WebView without its permission (Telegram's) still takes execCommand.
async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the older path
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const done = document.execCommand('copy');
    document.body.removeChild(area);
    return done;
  } catch {
    return false;
  }
}

type CopyButtonProps = {
  /** What is copied, in its canonical form (Latin digits, no separators). */
  value: string;
  /** Names the button («کپی شماره کارت»). */
  label: string;
  /** Replaces the label for a moment after a copy. Defaults to «کپی شد». */
  doneLabel?: string;
  variant?: ButtonProps['variant'];
  size?: ButtonProps['size'];
  className?: string;
  'data-testid'?: string;
};

// Copies `value` and says so in words, to the eye and to a screen reader (a polite live region). When
// nothing could be copied it says that too, on screen: the person copies the shown value by hand. The
// failure stays until the next press; a success fades after a moment.
export function CopyButton({
  value,
  label,
  doneLabel = t.common.copied,
  variant = 'secondary',
  size = 'sm',
  className,
  'data-testid': testId,
}: CopyButtonProps) {
  const [state, setState] = useState<'idle' | 'done' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  async function copy() {
    const done = await writeClipboard(value);
    setState(done ? 'done' : 'failed');
    if (timer.current) clearTimeout(timer.current);
    if (done) timer.current = setTimeout(() => setState('idle'), 2500);
  }

  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={className}
        data-testid={testId}
        data-state={state}
        onPress={copy}
      >
        {state === 'done' ? (
          <CheckIcon />
        ) : state === 'failed' ? (
          <DangerIcon />
        ) : (
          <CopyIcon />
        )}
        {state === 'done' ? doneLabel : label}
      </Button>
      {/* The one live region: a success is heard, a failure is also read, on its own line. */}
      <span
        role="status"
        aria-live="polite"
        className={
          state === 'failed'
            ? 'block w-full text-sm leading-6 text-danger'
            : 'sr-only'
        }
      >
        {state === 'done'
          ? doneLabel
          : state === 'failed'
            ? t.common.copyFailedByHand
            : ''}
      </span>
    </>
  );
}
