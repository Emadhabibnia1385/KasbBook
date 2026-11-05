'use client';

import { Drawer } from '@heroui/react';
import {
  type ReactNode,
  type RefObject,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { tv } from 'tailwind-variants';
import { t } from '../strings';
import { useRegisterOverlay } from '../providers/overlays';

const bottomSheet = tv({
  slots: {
    // In Telegram the visible height is --tg-viewport-stable-height; the sheet clears the bottom bars.
    dialog:
      'mx-auto max-h-[min(85dvh,var(--tg-viewport-stable-height,100dvh))] pr-[max(1.5rem,var(--nasim-safe-right))] pb-[max(1.5rem,var(--nasim-safe-bottom))] pl-[max(1.5rem,var(--nasim-safe-left))] sm:max-w-lg sm:rounded-b-none',
    header: 'gap-1',
    // A scrolling region must be keyboard-reachable; the ring is inside so the edge cannot clip it.
    body: 'rounded-lg focus-visible:-outline-offset-2',
    description: 'text-sm text-muted text-pretty',
    // Buttons fill the width on phones
    footer:
      'flex-col gap-2 empty:hidden sm:flex-row sm:justify-end [&>.button]:w-full sm:[&>.button]:w-fit',
  },
});

// A backdrop press is ignored this long after the content changes height: the tapped button moved.
export const SETTLE_MS = 500;

type SheetBodyProps = {
  title: string;
  quietUntil: RefObject<number>;
  children: ReactNode;
};

// The body is a named, focusable section only when it scrolls, measured on open and on each resize.
function SheetBody({ title, quietUntil, children }: SheetBodyProps) {
  const slots = bottomSheet();
  const content = useRef<HTMLDivElement>(null);
  const [scrolls, setScrolls] = useState(false);
  useLayoutEffect(() => {
    const inner = content.current;
    const box = inner?.parentElement;
    if (!inner || !box) return;
    let height = -1;
    const measure = () => {
      setScrolls(box.scrollHeight > box.clientHeight + 1);
      if (inner.offsetHeight === height) return;
      height = inner.offsetHeight;
      quietUntil.current = performance.now() + SETTLE_MS;
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    observer.observe(inner);
    // A step that swaps its content is seen at once; the resize observer reports a frame later.
    const swaps = new MutationObserver(measure);
    swaps.observe(inner, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      swaps.disconnect();
    };
  }, [quietUntil]);
  return (
    <Drawer.Body
      render={(props) => <section {...props} />}
      aria-label={scrolls ? title : undefined}
      tabIndex={scrolls ? 0 : undefined}
      className={slots.body()}
    >
      <div ref={content}>{children}</div>
    </Drawer.Body>
  );
}

type BottomSheetProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  /** Action buttons; the sheet closes on Escape, backdrop tap, drag down or the close button. */
  footer?: ReactNode;
  /** `false` for a flow that moves money: only its own buttons, Escape and Back close the sheet. */
  isDismissable?: boolean;
  /** A request is running: the backdrop and a drag down are ignored until it is over. */
  isBusy?: boolean;
};

export function BottomSheet({
  isOpen,
  onOpenChange,
  title,
  description,
  children,
  footer,
  isDismissable = true,
  isBusy = false,
}: BottomSheetProps) {
  const slots = bottomSheet();
  const quietUntil = useRef(0);
  useRegisterOverlay(isOpen, () => onOpenChange(false));
  return (
    <Drawer.Backdrop
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable={isDismissable && !isBusy}
      shouldCloseOnInteractOutside={() =>
        performance.now() >= quietUntil.current
      }
    >
      <Drawer.Content placement="bottom">
        <Drawer.Dialog className={slots.dialog()}>
          <Drawer.Handle />
          <Drawer.CloseTrigger aria-label={t.common.close} />
          <Drawer.Header className={slots.header()}>
            <Drawer.Heading>{title}</Drawer.Heading>
            {description ? (
              <p className={slots.description()}>{description}</p>
            ) : null}
          </Drawer.Header>
          <SheetBody title={title} quietUntil={quietUntil}>
            {children}
          </SheetBody>
          {footer ? (
            <Drawer.Footer className={slots.footer()}>{footer}</Drawer.Footer>
          ) : null}
        </Drawer.Dialog>
      </Drawer.Content>
    </Drawer.Backdrop>
  );
}
