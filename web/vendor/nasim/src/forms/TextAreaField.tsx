'use client';

import {
  Description,
  FieldError,
  Label,
  TextArea,
  TextField as HeroTextField,
} from '@heroui/react';
import type { ComponentProps } from 'react';
import {
  type Binding,
  type FieldProps,
  WithBinding,
  describes,
} from './binding';

type TextAreaFieldProps = FieldProps &
  Binding<string> &
  Pick<
    ComponentProps<typeof TextArea>,
    'placeholder' | 'rows' | 'maxLength' | 'autoFocus'
  > & {
    /** "ltr" for a value that is code or a list of addresses. */
    dir?: 'ltr';
  };

// A multi-line TextField: notes, ticket messages. The value is the text as typed.
export function TextAreaField({
  label,
  description,
  isRequired,
  isDisabled,
  className,
  'data-testid': testId,
  rows = 4,
  dir,
  placeholder,
  maxLength,
  autoFocus,
  ...binding
}: TextAreaFieldProps) {
  return (
    <WithBinding<string> binding={binding as Binding<string>}>
      {(field) => (
        <HeroTextField
          {...describes(description)}
          fullWidth
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
          <TextArea
            ref={field.inputRef}
            fullWidth
            dir={dir}
            rows={rows}
            placeholder={placeholder}
            maxLength={maxLength}
            autoFocus={autoFocus}
          />
          {description ? <Description>{description}</Description> : null}
          <FieldError>{field.errorMessage}</FieldError>
        </HeroTextField>
      )}
    </WithBinding>
  );
}
