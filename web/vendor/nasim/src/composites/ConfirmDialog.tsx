'use client';

import { AlertDialog } from '@heroui/react';
import { type ReactNode, useState } from 'react';
import { t } from '../strings';
import { Button, Spinner } from '../primitives';
import { useRegisterOverlay } from '../providers/overlays';

type ConfirmDialogProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  title: string;
  /** What happens, what it affects, and whether it can be undone. */
  description?: ReactNode;
  /** The same as `description`, for a body of several paragraphs. */
  children?: ReactNode;
  /** Name the action («حذف سرویس»), not just «تأیید». */
  confirmLabel?: string;
  cancelLabel?: string;
  /** "danger" for destructive or irreversible actions. */
  tone?: 'default' | 'danger';
  /** May return a promise: the dialog waits, then closes; on rejection it stays open (report it). */
  onConfirm: () => void | Promise<unknown>;
  /**
   * The owner knows when the action is running (a mutation's `isPending`): the dialog then only shows
   * it, does not wait for `onConfirm` and does not close itself; close it when the action succeeds.
   */
  isPending?: boolean;
};

export function ConfirmDialog({
  isOpen,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel = t.common.confirm,
  cancelLabel = t.common.cancel,
  tone = 'default',
  onConfirm,
  isPending,
}: ConfirmDialogProps) {
  const [running, setRunning] = useState(false);
  const owned = isPending !== undefined;
  const pending = owned ? isPending : running;
  useRegisterOverlay(isOpen, () => {
    if (!pending) onOpenChange(false);
  });
  async function confirm() {
    if (owned) {
      // The owner reports a failure of its own action; this only starts it.
      Promise.resolve(onConfirm()).catch(() => {});
      return;
    }
    setRunning(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch {
      // The caller reports its failure (a toast, onError); the dialog stays open for a retry.
    } finally {
      setRunning(false);
    }
  }
  const body = description || children;
  return (
    <AlertDialog.Backdrop
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable={!pending}
      isKeyboardDismissDisabled={pending}
    >
      <AlertDialog.Container>
        <AlertDialog.Dialog className="sm:max-w-sm">
          <AlertDialog.Header>
            <AlertDialog.Icon
              status={tone === 'danger' ? 'danger' : 'accent'}
            />
            <AlertDialog.Heading>{title}</AlertDialog.Heading>
          </AlertDialog.Header>
          {body ? (
            <AlertDialog.Body>
              {description ? (
                <div className="text-pretty">{description}</div>
              ) : null}
              {children}
            </AlertDialog.Body>
          ) : null}
          <AlertDialog.Footer>
            <Button
              slot="close"
              size="lg"
              variant="tertiary"
              isDisabled={pending}
            >
              {cancelLabel}
            </Button>
            <Button
              size="lg"
              variant={tone === 'danger' ? 'danger' : 'primary'}
              isPending={pending}
              onPress={confirm}
            >
              {({ isPending: showSpinner }) => (
                <>
                  {showSpinner ? <Spinner color="current" size="sm" /> : null}
                  {confirmLabel}
                </>
              )}
            </Button>
          </AlertDialog.Footer>
        </AlertDialog.Dialog>
      </AlertDialog.Container>
    </AlertDialog.Backdrop>
  );
}
