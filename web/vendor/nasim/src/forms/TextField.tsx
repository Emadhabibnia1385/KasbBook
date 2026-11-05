'use client';

import {
  Description,
  FieldError,
  Input,
  Label,
  TextField as HeroTextField,
} from '@heroui/react';
import type { ComponentProps } from 'react';
import {
  type Binding,
  type FieldProps,
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
    /** "ltr" for emails, usernames and phone numbers: Latin text types and aligns correctly. */
    dir?: 'ltr';
  };

// In a form by `name`, or controlled by `value` and `onChange` (a filter, a dialog, a flow).
export function TextField({
  label,
  description,
  isRequired,
  isDisabled,
  className,
  'data-testid': testId,
  dir,
  type,
  placeholder,
  autoComplete,
  inputMode,
  maxLength,
  minLength,
  autoFocus,
  spellCheck,
  ...binding
}: TextFieldProps) {
  return (
    <WithBinding<string> binding={binding as Binding<string>}>
      {(field) => (
        <HeroTextField
          fullWidth
          {...describes(description)}
          name={field.name}
          value={field.value ?? ''}
          onChange={field.onChange}
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
            ref={field.inputRef}
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
      )}
    </WithBinding>
  );
}
