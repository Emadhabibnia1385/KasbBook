'use client';

import {
  Description,
  FieldError,
  Input,
  Label,
  TextField as HeroTextField,
} from '@heroui/react';
import {
  type ComponentProps,
  useCallback,
  useLayoutEffect,
  useRef,
} from 'react';
import { caretAfter, group, significantBefore, ungroup } from './grouping';
import {
  type Binding,
  type FieldProps,
  type FieldState,
  WithBinding,
  describes,
} from './binding';

type TextFieldProps = FieldProps &
  Binding<string> &
  Pick<
    ComponentProps<typeof Input>,
    | 'type'
    | 'placeholder'
    | 'autoComplete'
    | 'inputMode'
    | 'maxLength'
    | 'minLength'
    | 'autoFocus'
    | 'spellCheck'
  > & {
    /**
     * A box that takes an amount (`inputMode="decimal"`) shows it with a separator every three digits as
     * it is typed; the value the form keeps stays the plain digits. `false` turns that off.
     */
    grouped?: boolean;
    /** "ltr" for emails, usernames and phone numbers: Latin text types and aligns correctly. */
    dir?: 'ltr';
  };

type ViewProps = Omit<FieldProps, 'className' | 'data-testid'> &
  Pick<
    TextFieldProps,
    | 'dir'
    | 'type'
    | 'placeholder'
    | 'autoComplete'
    | 'inputMode'
    | 'maxLength'
    | 'minLength'
    | 'autoFocus'
    | 'spellCheck'
  > & {
    field: FieldState<string>;
    grouping: boolean;
    className?: string;
    testId?: string;
  };

// The box itself. It is apart from `TextField` because it keeps the caret where the person was typing
// while separators appear and go, which needs hooks, and the field's render function cannot hold any.
function TextFieldView({
  field,
  grouping,
  label,
  description,
  isRequired,
  isDisabled,
  className,
  testId,
  dir,
  type,
  placeholder,
  autoComplete,
  inputMode,
  maxLength,
  minLength,
  autoFocus,
  spellCheck,
}: ViewProps) {
  const element = useRef<HTMLInputElement | null>(null);
  const caret = useRef<number | null>(null);
  const shown = grouping ? group(field.value ?? '') : (field.value ?? '');

  const setRef = useCallback(
    (node: HTMLInputElement | null) => {
      element.current = node;
      field.inputRef?.(node);
    },
    [field.inputRef],
  );

  // Once the new text is drawn, put the caret back after the same digit it was after.
  useLayoutEffect(() => {
    const node = element.current;
    if (caret.current === null || !node || document.activeElement !== node) return;
    const place = caretAfter(shown, caret.current);
    caret.current = null;
    node.setSelectionRange(place, place);
  }, [shown]);

  const change = (text: string) => {
    if (!grouping) {
      field.onChange(text);
      return;
    }
    const node = element.current;
    if (node && node.selectionStart !== null) {
      caret.current = significantBefore(text, node.selectionStart);
    }
    field.onChange(ungroup(text));
  };

  return (
    <HeroTextField
      fullWidth
      {...describes(description)}
      name={field.name}
      value={shown}
      onChange={change}
      onBlur={field.onBlur}
      isInvalid={field.isInvalid}
      isRequired={isRequired}
      isDisabled={isDisabled}
      validationBehavior="aria"
      className={className}
      data-testid={testId}
    >
      <Label>{label}</Label>
      <Input
        ref={setRef}
        dir={dir}
        className={dir === 'ltr' ? 'text-end' : undefined}
        type={type}
        placeholder={placeholder}
        autoComplete={autoComplete}
        inputMode={inputMode}
        maxLength={maxLength}
        minLength={minLength}
        autoFocus={autoFocus}
        spellCheck={spellCheck}
      />
      {description ? <Description>{description}</Description> : null}
      <FieldError>{field.errorMessage}</FieldError>
    </HeroTextField>
  );
}

// In a form by `name`, or controlled by `value` and `onChange` (a filter, a dialog, a flow).
export function TextField({
  className,
  'data-testid': testId,
  grouped = true,
  inputMode,
  ...rest
}: TextFieldProps) {
  const { name, value, onChange, errorMessage, ...view } = rest as TextFieldProps & {
    name?: string;
    value?: string;
    onChange?: (value: string) => void;
    errorMessage?: string | null;
  };
  const binding = { name, value, onChange, errorMessage } as Binding<string>;
  return (
    <WithBinding<string> binding={binding}>
      {(field) => (
        <TextFieldView
          {...view}
          field={field}
          grouping={grouped && inputMode === 'decimal'}
          inputMode={inputMode}
          className={className}
          testId={testId}
        />
      )}
    </WithBinding>
  );
}
