'use client';

import { Form } from '@heroui/react';
import { type ComponentProps, type ReactNode, useRef } from 'react';
import {
  type FieldValues,
  FormProvider,
  type SubmitHandler,
  type UseFormReturn,
  useFormState,
} from 'react-hook-form';
import './persianZod';
import { BoundFieldContext } from './binding';
import { BoundField } from './boundField';
import { SubmittingContext } from './submitting';

type FormRootProps<T extends FieldValues> = Omit<
  ComponentProps<typeof Form>,
  'onSubmit'
> & {
  form: UseFormReturn<T>;
  /** Runs with the validated values. Handle failures inside it (e.g. `mutate`, not `mutateAsync`). */
  onSubmit: SubmitHandler<T>;
};

// One <form> for React Hook Form + Zod: context for fields, ARIA-only validation, no double submit.
export function FormRoot<T extends FieldValues>({
  form,
  onSubmit,
  children,
  ...props
}: FormRootProps<T>) {
  const running = useRef(false);
  // Subscribed here, in the component that renders the form, so it re-renders by itself.
  const { isSubmitting } = useFormState({ control: form.control });
  const submit = form.handleSubmit(onSubmit);
  return (
    <FormProvider {...form}>
      <BoundFieldContext value={BoundField}>
        <SubmittingContext value={isSubmitting}>
          <Form
            validationBehavior="aria"
            {...props}
            onSubmit={(event) => {
              if (running.current) {
                event.preventDefault();
                return;
              }
              running.current = true;
              return submit(event).finally(() => {
                running.current = false;
              });
            }}
          >
            {children}
          </Form>
        </SubmittingContext>
      </BoundFieldContext>
    </FormProvider>
  );
}

/**
 * The fields of a form whose submit lives elsewhere (Telegram's MainButton, a sheet's footer): they bind
 * by `name` as in `FormRoot`, with no `<form>` of its own, so a small form of its own may sit inside.
 */
export function FormFields<T extends FieldValues>({
  form,
  children,
}: {
  form: UseFormReturn<T>;
  children: ReactNode;
}) {
  return (
    <FormProvider {...form}>
      <BoundFieldContext value={BoundField}>{children}</BoundFieldContext>
    </FormProvider>
  );
}
