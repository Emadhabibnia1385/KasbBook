'use client';

import { Modal as HeroModal } from '@heroui/react';
import type { ReactNode } from 'react';
import { useRegisterOverlay } from '../providers/overlays';
import { t } from '../strings';

type ModalProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  title: ReactNode;
  children: ReactNode;
  /** Action buttons: the cancel first, the main action last. */
  footer?: ReactNode;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  /** `false` for a form with unsaved input: a backdrop press and Escape close nothing. */
  isDismissable?: boolean;
  /** A request is running: the backdrop and Escape are ignored until it is over. */
  isBusy?: boolean;
};

// A centred dialog for a form or a detail (BottomSheet is the phone's). Focus is trapped and restored
// by React Aria; the host's Back button closes it as the top layer.
export function Modal({
  isOpen,
  onOpenChange,
  title,
  children,
  footer,
  size = 'md',
  isDismissable = true,
  isBusy = false,
}: ModalProps) {
  useRegisterOverlay(isOpen, () => {
    if (!isBusy) onOpenChange(false);
  });
  const closable = isDismissable && !isBusy;
  return (
    <HeroModal.Backdrop
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable={closable}
      isKeyboardDismissDisabled={!closable}
    >
      <HeroModal.Container size={size}>
        <HeroModal.Dialog>
          <HeroModal.CloseTrigger aria-label={t.common.close} />
          <HeroModal.Header>
            <HeroModal.Heading>{title}</HeroModal.Heading>
          </HeroModal.Header>
          <HeroModal.Body>{children}</HeroModal.Body>
          {footer ? <HeroModal.Footer>{footer}</HeroModal.Footer> : null}
        </HeroModal.Dialog>
      </HeroModal.Container>
    </HeroModal.Backdrop>
  );
}
