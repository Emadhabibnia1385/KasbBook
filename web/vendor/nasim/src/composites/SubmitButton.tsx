'use client';

import type { ReactNode } from 'react';
import { useSubmitting } from '../forms/submitting';
import { Button, type ButtonProps, Spinner } from '../primitives';

type SubmitButtonProps = Omit<ButtonProps, 'children' | 'type'> & {
  children: ReactNode;
};

// The form's submit button: in FormRoot it spins while submitting and cannot submit twice. It is
// disabled while it runs, not React Aria's `isPending`: that announces the button by
// its own id, and a form that closes or is replaced on success leaves the announcement pointing at a
// removed element for a few seconds (axe: role-img-alt).
export function SubmitButton({
  children,
  isPending,
  isDisabled,
  ...props
}: SubmitButtonProps) {
  const submitting = useSubmitting();
  const pending = isPending ?? submitting;
  return (
    <Button
      type="submit"
      size="lg"
      fullWidth
      {...props}
      isDisabled={isDisabled || pending}
    >
      {pending ? (
        <Spinner color="current" size="sm" aria-hidden="true" />
      ) : null}
      {children}
    </Button>
  );
}
