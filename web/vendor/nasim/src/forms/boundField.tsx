'use client';

import type { ReactNode } from 'react';
import { useController } from 'react-hook-form';
import type { BoundField as BoundFieldType, FieldState } from './binding';

// A field named in a form: React Hook Form owns its value, its blur and its error.
export const BoundField: BoundFieldType = function BoundField<V>({
  name,
  children,
}: {
  name: string;
  children: (state: FieldState<V>) => ReactNode;
}) {
  const { field, fieldState } = useController({ name });
  return children({
    value: field.value,
    // "Nothing chosen" is undefined in a form, so a schema's required message is the one shown.
    onChange: (value) => field.onChange(value === null ? undefined : value),
    onBlur: field.onBlur,
    inputRef: field.ref,
    isInvalid: fieldState.invalid,
    errorMessage: fieldState.error?.message,
    name,
  });
};
