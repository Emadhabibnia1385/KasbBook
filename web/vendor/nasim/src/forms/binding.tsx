'use client';

import { createContext, type ReactNode, use } from 'react';

/** What every field shows, wherever its value lives. */
export type FieldProps = {
  label: ReactNode;
  description?: ReactNode;
  isRequired?: boolean;
  isDisabled?: boolean;
  /** Reaches the field's root element, for a layout or a test. */
  className?: string;
  'data-testid'?: string;
};

/**
 * Spread on a field's React Aria root: React Aria links a control to its description when the field
 * mounts and again only when told that a description exists, so a hint that appears later (the hint of
 * the option just chosen) would describe nothing. HeroUI's types leave the prop off some fields,
 * though it reaches React Aria on all of them.
 */
export const describes = (description: ReactNode): object => ({ description });

/** The field lives in a form (`FormRoot`): its `name` is the key in the form values. */
export type Bound = {
  name: string;
  value?: undefined;
  onChange?: undefined;
  errorMessage?: undefined;
};

/**
 * The field's owner keeps the value (a filter, a dialog, a flow with its own state): it passes
 * `value` and `onChange`, and the message to show under the field in `errorMessage`.
 */
export type Controlled<V> = {
  value: V;
  onChange: (value: V) => void;
  /** `null` and `undefined` both mean "no error", so a lookup that finds nothing can pass straight through. */
  errorMessage?: string | null;
  /** Names the control for the browser (autofill, a native form post); optional here. */
  name?: string;
};

export type Binding<V> = Bound | Controlled<V>;

/** The value, its setter and its error as a field draws them, from either kind of owner. */
export type FieldState<V> = {
  value: V | undefined;
  onChange: (value: V) => void;
  onBlur?: () => void;
  /** Gives a form the element to focus on the first invalid field. */
  inputRef?: (element: HTMLElement | null) => void;
  isInvalid: boolean;
  errorMessage?: string | null;
  name?: string;
};

/** How a field named in a form reads and writes its value; `FormRoot` provides it. */
export type BoundField = <V>(props: {
  name: string;
  children: (state: FieldState<V>) => ReactNode;
}) => ReactNode;

// React Hook Form sits behind this context, in `FormRoot`'s own modules, so a page whose fields are
// all controlled (a filter, a dialog) never loads it.
export const BoundFieldContext = createContext<BoundField | null>(null);

/** Hands a field its state from the form it is in or from its owner, so a field draws once. */
export function WithBinding<V>({
  binding,
  children,
}: {
  binding: Binding<V>;
  children: (state: FieldState<V>) => ReactNode;
}) {
  const Bound = use(BoundFieldContext);
  if (binding.onChange) {
    return children({
      value: binding.value,
      onChange: binding.onChange,
      isInvalid: Boolean(binding.errorMessage),
      errorMessage: binding.errorMessage,
      name: binding.name,
    });
  }
  if (!Bound)
    throw new Error(
      `The field "${binding.name}" has a name but no FormRoot around it: put it in a FormRoot, or give it value and onChange.`,
    );
  return <Bound<V> name={binding.name}>{children}</Bound>;
}
