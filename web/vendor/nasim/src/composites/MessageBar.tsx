'use client';

import {
  type KeyboardEvent,
  type ReactNode,
  useLayoutEffect,
  useRef,
} from 'react';
import { SendIcon } from '../icons';
import { Button, Spinner } from '../primitives';

type ComposingProps = {
  /** Names the text box («پیام شما»); it is also its placeholder. */
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  /** Enter, or the send button. */
  onSubmit: () => void;
  sendLabel: string;
  /** There is something to send (words or a file). */
  canSend: boolean;
  isSending?: boolean;
  maxLength?: number;
  /** The attach button, at the start of the row. */
  leading?: ReactNode;
  /** What is attached, above the row. */
  attachment?: ReactNode;
  /** A refusal or a hint, above the row. */
  notice?: ReactNode;
};

type ClosedProps = {
  /** The conversation is over: the bar says this and offers no field. */
  closedNote: string;
};

// The text box grows with its words up to this many lines, then scrolls
const MAX_LINES = 5;

function useAutoGrow(value: string) {
  const area = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) return;
    element.style.height = 'auto';
    const line = Number.parseFloat(getComputedStyle(element).lineHeight) || 24;
    element.style.height = `${Math.min(element.scrollHeight, line * MAX_LINES)}px`;
  }, [value]);
  return area;
}

function Composing({
  label,
  value,
  onValueChange,
  onSubmit,
  sendLabel,
  canSend,
  isSending = false,
  maxLength,
  leading,
  attachment,
  notice,
}: ComposingProps) {
  const area = useAutoGrow(value);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key !== 'Enter' ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    )
      return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend && !isSending) onSubmit();
      }}
    >
      {attachment}
      {notice}
      <div
        data-nasim-field-box
        className="flex items-end gap-1 rounded-3xl border border-(--field-border) bg-surface p-1.5 focus-within:border-focus"
      >
        {leading}
        <textarea
          ref={area}
          rows={1}
          dir="auto"
          value={value}
          maxLength={maxLength}
          aria-label={label}
          placeholder={label}
          enterKeyHint="send"
          onChange={(event) => onValueChange(event.currentTarget.value)}
          onKeyDown={onKeyDown}
          className="min-h-10 min-w-0 flex-1 resize-none bg-transparent px-2 py-2 leading-6 text-foreground outline-none placeholder:text-muted"
        />
        <Button
          type="submit"
          isIconOnly
          variant="primary"
          className="rounded-full"
          aria-label={sendLabel}
          isDisabled={!canSend}
          isPending={isSending}
        >
          {({ isPending }) =>
            isPending ? <Spinner color="current" size="sm" /> : <SendIcon />
          }
        </Button>
      </div>
    </form>
  );
}

// A chat's compact composer: attach, a growing text box and send in one row; Enter sends.
export function MessageBar(props: ComposingProps | ClosedProps) {
  if ('closedNote' in props) {
    return (
      <p className="rounded-2xl bg-default px-4 py-3 text-sm text-muted text-pretty">
        {props.closedNote}
      </p>
    );
  }
  return <Composing {...props} />;
}
