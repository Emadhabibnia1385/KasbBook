'use client';

import { Label, TextField } from '@heroui/react';
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { t } from '../strings';
import { CheckIcon, CopyIcon } from '../icons';
import { Button, TextArea, toast } from '../primitives';

type CopyFieldProps = {
  label: string;
  /** A value to hand over: subscription link, wallet address, card number. */
  value: string;
  /** A value of several lines (a WireGuard profile): shown whole in its own box, copied whole. */
  multiline?: boolean;
  /** Whatever belongs to the value, shown under its field (a QR code, a pager). */
  children?: ReactNode;
};

// The last characters stay visible when a long value is cut, as they tell one link from another.
const TAIL = 8;

// Copies `value`; when the clipboard is refused it selects the text and says to copy it by hand.
function useCopy(value: string, select: () => void) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(t.common.copied);
    } catch {
      select();
      toast.danger(t.common.copyFailed, {
        description: t.common.copyFailedHint,
      });
    }
  }
  return { copied, copy };
}

// A read-only value in a field that copies on a press anywhere in it. Always left to right.
export function CopyField({
  label,
  value,
  multiline = false,
  children,
}: CopyFieldProps) {
  const shown = useRef<HTMLSpanElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const { copied, copy } = useCopy(value, () => {
    if (multiline) return area.current?.select();
    const range = document.createRange();
    if (shown.current) range.selectNodeContents(shown.current);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
  });

  if (multiline) {
    return (
      <div className="flex flex-col gap-2">
        <TextField fullWidth isReadOnly value={value}>
          <div className="flex items-center justify-between gap-2">
            <Label>{label}</Label>
            <Button
              isIconOnly
              size="sm"
              variant="ghost"
              aria-label={t.common.copyOf(label)}
              onPress={copy}
            >
              {copied ? <CheckIcon /> : <CopyIcon />}
            </Button>
          </div>
          <TextArea
            ref={area}
            fullWidth
            dir="ltr"
            rows={Math.min(10, Math.max(3, value.split('\n').length))}
            className="text-start font-mono text-sm"
            onFocus={(event) => event.currentTarget.select()}
          />
        </TextField>
        {children}
      </div>
    );
  }

  const cut = value.length > TAIL * 2 ? value.length - TAIL : value.length;
  return (
    <div className="flex flex-col gap-2">
      <span aria-hidden className="text-sm font-medium text-muted">
        {label}
      </span>
      <Button
        fullWidth
        variant="secondary"
        className="h-auto min-h-12 justify-between gap-3 px-4 py-2 font-normal"
        onPress={copy}
      >
        <span className="sr-only">{t.common.copyOf(label)}</span>
        <span
          ref={shown}
          dir="ltr"
          className="flex min-w-0 flex-1 justify-end font-mono text-sm select-text"
        >
          <span className="truncate">{value.slice(0, cut)}</span>
          <span className="shrink-0">{value.slice(cut)}</span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-sm font-medium">
          <span className="text-accent">
            {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
          </span>
          {copied ? t.common.copied : t.common.copy}
        </span>
      </Button>
      {children}
    </div>
  );
}
